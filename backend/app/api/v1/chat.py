import json
from typing import List

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage, ToolMessage
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import clock
from app.db.models.user import User
from app.db.session import get_db, SessionLocal
from app.schemas.chat_schema import (
    ChatRecordOut,
    ChatRequest,
    ConversationOut,
    ConversationUpdate,
)
from app.schemas.preference_schema import PreferenceIn, PreferenceOut
from app.services import chat_service, conversation_service, preference_service
from app.services.plan_context import build_plan_brief, load_linked_plan, plan_label
from app.llm.deepseek_client import get_thinking_llm
from app.llm.prompts import SIMPLIFIED_CHINESE_RULE
from app.rag.retriever import retrieve_knowledge
from app.tools.time_tool import get_current_datetime
from app.tools.web_search_tool import web_search

router = APIRouter(prefix="/chat", tags=["AI 对话"])

# 对话先联网查，查不到才回退到本地知识库；关联了行程时以行程内容为准，只在需要实时信息时联网
CHAT_TOOL_MAP = {
    web_search.name: web_search,
    # 以前只绑了 web_search，助手被问「现在几点」只能搜网页，搜不到就说自己不知道时间
    get_current_datetime.name: get_current_datetime,
}
# web_search 降级时返回的提示语，出现这些就说明没拿到真实数据
DEGRADED_MARKERS = ("联网搜索暂不可用", "未配置 Tavily", "未返回有效结果")

# 助手性格与回答长度：前端侧面板的选项映射到这里的指令
PERSONA_STYLES = {
    "professional": "你是一位严谨专业的旅行顾问：建议要有依据、条理清晰，不确定的信息必须说明，不要编造。",
    "humorous": "你是一位幽默风趣的旅行搭子：语气轻松、可以适当开玩笑，但价格、时间、注意事项等关键信息必须准确。",
    "caring": "你是一位贴心细致的旅行管家：主动提醒容易被忽略的细节（证件、天气、排队、老人小孩、饮食忌口），语气温和耐心。",
    "concise": "你是一位极简高效的助手：先给结论再给必要理由，能一句话说清就不写三句，直接给可执行的信息。",
}
PERSONA_DEFAULT = "你是一位专业、友好的旅行助手。"

LENGTH_HINTS = {
    "short": "回答控制在三句话以内。",
    "medium": "回答控制在 150 字左右，重点突出。",
    "long": "可以展开说明、分点讲清楚，但不要罗列无关内容。",
}

# 无论选哪种性格（含自定义）都保留的底线，自定义风格不能把它覆盖掉
GUARDRAIL = (
    "价格、门票、时间等关键信息必须准确；不确定就说不确定，不要编造。\n"
    # 联网搜到的台湾/香港资料常是繁体，不写死这条，回答会跟着变繁体
    + SIMPLIFIED_CHINESE_RULE
)
CUSTOM_PERSONA_LIMIT = 120

# 单轮对话最多执行的联网搜索次数，超出的调用回一条说明而不是直接丢弃
MAX_SEARCHES = 2


def resolve_style(persona: str | None, custom_persona: str | None = None) -> str:
    if persona == "custom":
        text = " ".join(str(custom_persona or "").split())[:CUSTOM_PERSONA_LIMIT]
        if text:
            return f"用户自定义的风格要求（优先遵守）：{text}"
    return PERSONA_STYLES.get(persona or "", PERSONA_DEFAULT)


def current_time_block() -> str:
    """把业务时区的当前时间直接写进提示词。

    只绑工具不够：模型经常不调工具就答「我不知道现在几点」，而联网搜「北京时间」
    搜回来的多半是时区介绍而不是当前时间。提示词里先给一份权威时间，
    模型就能直接回答，需要换算时差时再调 get_current_datetime。
    """
    current = clock.now()
    return (
        f"【当前时间】{current.strftime('%Y-%m-%d %H:%M:%S')}"
        f"（{clock.weekday_name(current)}，时区 {clock.timezone()}）\n"
        "这是服务器按业务时区取的真实时间，是回答时间问题的唯一依据。\n"
        "用户问「现在几点」「今天几号」「还有几天」时，直接用上面的时间回答，"
        "不要说「我没法知道现在几点」，也不要让用户自己去看手机或手表；\n"
        "问其他城市的时间，就按这个时间换算时差后回答。"
    )


def build_chat_prompt(
    message: str,
    history_text: str,
    rag_text: str = "",
    persona: str | None = None,
    answer_length: str | None = None,
    custom_persona: str | None = None,
    plan_brief: str = "",
) -> str:
    style = f"{resolve_style(persona, custom_persona)}\n{GUARDRAIL}"
    length = LENGTH_HINTS.get(answer_length or "", "")
    plan_block = (
        f"""
【关联行程】（用户本次选定的行程，回答前必须先读完）
{plan_brief}

【关联行程的使用要求】
1. 涉及这份行程的问题（第几天去哪、住哪、吃什么、预算多少、有什么注意事项），
   一律以【关联行程】里的内容为准，不要另编一份，也不要拿别的城市或别的日期来套；
2. 行程里已经写清楚的，直接据此回答，不需要联网；
3. 只有行程里没有、或者会随时间变化的信息（实时价格与预约规则、临时闭馆、未来天气、
   交通时刻）才调用 web_search 核实；核实结果与行程不一致时两个都说明，并指出哪个更新；
4. 行程里没写、联网也没查到的，直接说没有这项信息，不要编造。
"""
        if plan_brief
        else ""
    )
    priority_block = (
        """【回答依据的优先级】
1. 与【关联行程】有关的问题，先依据行程里的内容回答。
2. 行程里没有、或会随时间变化的信息，再联网查证补充。
3. 联网也查不到时，参考【本地知识库】；都没有依据就直接说"这个我查不到"，不要凭记忆编造具体数字。"""
        if plan_brief
        else """【回答依据的优先级】
1. 优先依据【联网搜索结果】回答；价格、门票、时间、预约规则等实时信息必须先联网查证。
2. 联网搜索没查到、或结果与问题无关时，才参考【本地知识库】。
3. 两者都没有依据时，直接说"这个我查不到"，不要凭记忆编造具体数字。
知识库内容只在相关时参考；如果问的是别的城市，请忽略它，不要把它当成用户要去的地方。"""
    )
    knowledge_block = (
        f"""
【本地知识库】（联网搜索没查到时的兜底资料）
{rag_text}
"""
        if rag_text
        else ""
    )
    return f"""{style}
{length}
{current_time_block()}
请根据以下信息回答用户的问题。
{plan_block}
【历史对话】
{history_text}
{knowledge_block}
【用户问题】
{message}

{priority_block}

【检索范围】

"""


def _resolve_conversation(
    db: Session,
    current_user: User,
    body: ChatRequest,
):
    """定位本次对话所属的会话；没有就按这条消息新建一个。

    会话要在构造 StreamingResponse 之前就定下来：出错才能以干净的 JSON 404 返回，
    而不是流已经开了再往里塞一个 error 帧。
    """
    if body.conversation_id is None:
        return conversation_service.create_conversation(
            db,
            current_user.user_id,
            chat_service.make_title(body.message),
            seed=body,
        )

    conversation = conversation_service.get_conversation(
        db, current_user.user_id, body.conversation_id
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SSE 流式对话接口"""
    # 1. 定位会话
    conversation = _resolve_conversation(db, current_user, body)
    conversation_id = conversation.conversation_id

    # 2. 先取历史再存本次提问：反过来的话当前这句问题会同时出现在【历史对话】和
    #    【用户问题】里，白白重复一遍
    history = chat_service.get_conversation_messages(db, conversation_id, limit=6)
    history_text = "\n".join([f"{h.role}: {h.content}" for h in history])

    # 2.5 关联行程：先把行程内容读出来，后面要写进提示词。
    #     必须在返回 StreamingResponse 之前读——请求级的 db 在流里已经关闭
    linked_task, linked_plan = load_linked_plan(db, current_user.user_id, body.task_id)
    plan_brief = build_plan_brief(linked_task, linked_plan) if linked_task else ""
    plan_source = (
        {"title": "关联行程", "content": plan_label(linked_task)} if linked_task else None
    )

    # 3. 保存用户消息
    chat_service.save_chat_record(
        db,
        current_user.user_id,
        "user",
        body.message,
        body.task_id,
        conversation_id=conversation_id,
    )

    # 3. 流式生成：关联行程时先读行程、只在需要实时信息时才联网；
    #    没关联行程则「先联网搜索 → 搜不到再查本地知识库 → 都没有就说查不到」
    async def event_generator():
        llm = get_thinking_llm(temperature=0.7)
        full_response = ""

        def event(kind: str, data=None) -> str:
            return f"data: {json.dumps({'type': kind, 'data': data}, ensure_ascii=False)}\n\n"

        def degraded(text: str) -> bool:
            return any(marker in text for marker in DEGRADED_MARKERS)

        try:
            base_prompt = build_chat_prompt(
                message=body.message,
                history_text=history_text,
                persona=body.persona,
                answer_length=body.answer_length,
                custom_persona=body.custom_persona,
                plan_brief=plan_brief,
            )
            messages = [HumanMessage(content=base_prompt)]

            # 先把会话 id 报给前端：新会话是懒创建的，前端要靠这个 id 把它选进侧栏列表
            yield event("conversation", {"conversation_id": conversation_id})
            if plan_source:
                # 让用户看得见「这次回答读了哪份行程」，而不是只有一行提示文案
                yield event("sources", [plan_source])

            # 3.1 让模型自己决定要不要联网
            yield event("status", "正在阅读关联行程…" if plan_brief else "正在联网搜索…")
            planner = get_thinking_llm(temperature=0.2).bind_tools(
                [web_search, get_current_datetime]
            )
            plan = await planner.ainvoke(messages)
            calls = getattr(plan, "tool_calls", None) or []

            if calls:
                messages.append(plan)
            elif plan_brief:
                # 关联了行程：模型判断不用联网就直接基于行程回答。强制搜索会把行程里
                # 已经写清楚的答案冲成泛泛的搜索结果，也让「自主判断」名存实亡
                calls = []
            else:
                calls = [{"name": web_search.name, "args": {"query": body.message}, "id": "forced-search"}]

            # 3.2 执行工具调用（联网搜索最多两个，避免跑飞；时间工具不占搜索名额）
            search_results = []
            time_ok = False
            searches_done = 0
            for call in calls:
                name = call.get("name")
                args = call.get("args") or {}
                is_search = name == web_search.name

                if is_search and searches_done >= MAX_SEARCHES:
                    # 超出上限的调用也必须回一条 tool 消息：模型那条带 tool_calls 的
                    # 助手消息，每个 tool_call_id 都要有对应的 tool 消息回应，漏一个
                    # 后面整个请求都会被判为不合法（DeepSeek 直接 400）
                    messages.append(
                        ToolMessage(
                            content=f"本轮已达搜索上限（{MAX_SEARCHES} 次），该搜索未执行。"
                            "请基于已有结果回答，确实需要更多信息就说明还需要用户补充什么。",
                            tool_call_id=call.get("id"),
                        )
                    )
                    continue
                if is_search:
                    searches_done += 1

                yield event(
                    "status",
                    f"正在联网搜索：{args.get('query') or name}" if is_search else "正在获取当前时间…",
                )
                tool = CHAT_TOOL_MAP.get(name)
                try:
                    result = await anyio.to_thread.run_sync(tool.invoke, args) if tool else f"没有名为 {name} 的工具"
                except Exception as exc:
                    result = f"工具调用失败：{type(exc).__name__}: {exc}"
                text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
                if is_search:
                    search_results.append(text)
                elif tool is not None and "工具调用失败" not in text:
                    # 时间工具已经给出结果，不必再走「联网没查到」的降级提示
                    time_ok = True
                if call.get("id") != "forced-search":
                    messages.append(ToolMessage(content=text, tool_call_id=call.get("id")))
                else:
                    messages.append(HumanMessage(content=f"【联网搜索结果】\n{text}"))

            search_ok = bool(search_results) and any(not degraded(text) for text in search_results)

            # 3.3 联网查不到、且问的不是时间，才回头查本地知识库。
            #     关联行程时若模型压根没联网（行程里已有答案），就没有「搜不到」这回事
            if not search_ok and not time_ok and (searches_done or not plan_brief):
                yield event("status", "联网搜索没有结果，正在查本地知识库…")
                rag_context = await anyio.to_thread.run_sync(retrieve_knowledge, body.message, 3)
                if rag_context:
                    yield event(
                        "sources",
                        ([plan_source] if plan_source else [])
                        + [{"title": "本地知识库", "content": ctx[:50] + "..."} for ctx in rag_context],
                    )
                    messages.append(HumanMessage(
                        content="联网搜索没查到结果。以下是本地知识库内容，"
                                "若仍然与问题无关就直接说查不到，不要编造：\n" + "\n".join(rag_context)
                    ))

            yield event("status", "正在整理回答…")

            # 3.4 流式输出最终回答
            async for chunk in llm.astream(messages):
                content = chunk.content
                if content:
                    full_response += content
                    yield event("text", content)

            # 推送结束标记
            yield event("done")

        except Exception as e:
            yield event("error", str(e))

        finally:
            # 保存 AI 回复（流结束后落库）。这里必须用独立的 SessionLocal：请求级的 db
            # 此时已经关闭。conversation_id 取自闭包，不要在这里重新解析会话。
            if full_response:
                new_db = SessionLocal()
                try:
                    chat_service.save_chat_record(
                        new_db,
                        current_user.user_id,
                        "assistant",
                        full_response,
                        body.task_id,
                        conversation_id=conversation_id,
                    )
                finally:
                    new_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            # 显式禁止压缩：浏览器会声明 br/zstd，中间层若对响应做压缩，
            # 压缩器会把 SSE 憋在缓冲区里，前端要等整段结束才拿到内容
            "Content-Encoding": "identity",
        },
    )


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """会话历史列表，按最近活跃倒序"""
    rows = conversation_service.list_conversations(db, current_user.user_id, skip, limit)
    return [
        ConversationOut.model_validate(conversation).model_copy(
            update={"message_count": count, "last_message_time": last_time}
        )
        for conversation, count, last_time in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=List[ChatRecordOut])
def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """打开某个历史会话时加载它的消息"""
    conversation = conversation_service.get_conversation(
        db, current_user.user_id, conversation_id
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    return chat_service.get_conversation_messages(db, conversation.conversation_id)


@router.put("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: int,
    body: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重命名会话，或修改这个会话自己的助手设置"""
    conversation = conversation_service.get_conversation(
        db, current_user.user_id, conversation_id
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation_service.update_conversation(db, conversation, body)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除会话及其消息"""
    conversation = conversation_service.get_conversation(
        db, current_user.user_id, conversation_id
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    conversation_service.delete_conversation(db, conversation)


@router.get("/preferences", response_model=PreferenceOut)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取当前账号的助手设置；该账号还没设置过就先落默认值"""
    return preference_service.get_or_create_preference(db, current_user.user_id)


@router.put("/preferences", response_model=PreferenceOut)
def save_preferences(
    body: PreferenceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存当前账号的助手设置"""
    return preference_service.update_preference(db, current_user.user_id, body)