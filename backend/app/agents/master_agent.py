import json
from datetime import date
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from app.agents.graph.state import TravelAgentState
from app.agents.prompts import (
    RESEARCH_SUMMARY_PROMPT,
    RESEARCH_SYSTEM_PROMPT,
    itinerary_prompt,
    price_hints_prompt,
    research_kickoff_prompt,
)
from app.core.config import settings
from app.llm.deepseek_client import get_llm, get_thinking_llm
from app.rag.retriever import retrieve_knowledge
from app.tools.map_poi_tool import search_poi
from app.tools.weather_tool import query_weather
from app.tools.budget_tool import calculate_budget, calculate_budget_from_itinerary
from app.tools.time_tool import get_current_datetime
from app.tools.web_search_tool import web_search

# 让模型自己调用这些工具去查真实数据；预算与天气已在前面的确定性步骤里调过，不重复放进来
RESEARCH_TOOLS = [web_search, search_poi, get_current_datetime]
RESEARCH_TOOL_MAP = {tool.name: tool for tool in RESEARCH_TOOLS}
RESEARCH_MAX_STEPS = 4


# 定义 Pydantic 结构，强制大模型输出规范格式
class SpotPlan(BaseModel):
    name: str = Field(description="景点名称")
    ticket: Optional[float] = Field(
        None, description="门票价格（元/人），免费填 0；查不到真实价格就留空，不要凭记忆编造"
    )
    start_time: str = Field(description="建议到达时间，24 小时制，如 09:00")
    duration_minutes: int = Field(description="建议游玩时长（分钟）")
    opentime: Optional[str] = Field(
        None,
        description=(
            "开放时间，写成「08:30-17:00」并附闭馆日，如「08:30-17:00，周一闭馆」；"
            "只填【实时查询数据】里查到的，查不到就留空，不要凭印象编造"
        ),
    )


class MealPlan(BaseModel):
    name: str = Field(description="餐厅或档口名称")
    cost: Optional[float] = Field(
        None, description="人均花费（元）；查不到真实价格就留空，不要凭记忆编造"
    )
    reason: str = Field(description="推荐理由，要具体到招牌菜或特色")


class DayPlan(BaseModel):
    day: int = Field(description="第几天")
    description: str = Field(
        description=(
            "当天行程的文字说明，按内容重点分成 2-4 段：上午/下午/晚上的游玩节奏、"
            "餐饮安排、住宿与交通提示、注意事项各成一段；段与段之间必须用一个空行隔开"
            "不要写成一大段，也不要用「1. 2. 3.」这类列表符号"
        )
    )
    spots: List[SpotPlan] = Field(description="当天游玩的景点，按到访顺序排列")
    meals: List[MealPlan] = Field(description="当天推荐的餐饮")
    hotel: str = Field(description="当晚住宿")
    hotel_price: Optional[float] = Field(
        None,
        description="当晚住宿的实际房价（元/间/晚），取自【实时查询数据】；查不到留空，不要估算",
    )
    transport: str = Field(description="当天交通方式")
    transport_cost: Optional[float] = Field(
        None,
        description=(
            "当天市内交通的人均花费（元/人）：把当天要坐的地铁/公交/打车费用加起来，"
            "不是单程票价；取自【实时查询数据】；查不到留空，不要估算"
        ),
    )


class ItineraryOutput(BaseModel):
    destination: str
    days: List[DayPlan]
    summary: str = Field(
        description=(
            "行程总结，按内容重点分成 2-4 段（行程亮点、节奏与预算、注意事项各成一段），"
            "段与段之间必须用一个空行隔开（即两个换行符 \\n\\n），不要写成一大段"
        )
    )


class PriceHints(BaseModel):
    """从调研笔记里抽出来的真实价格，供预算工具优先采用"""

    hotel_price_per_room_night: Optional[float] = Field(
        None, description="住宿参考价（元/间/晚）；只有区间时取中位；笔记里没查到就留空"
    )
    hotel_price_text: Optional[str] = Field(
        None, description="住宿价格的原始描述（含区间与来源），如「600–1200 元/晚（Booking）」"
    )
    meal_per_person_per_day: Optional[float] = Field(
        None, description="餐饮人均每天（元），由笔记里的餐饮人均折算；没查到就留空"
    )
    transit_per_person_per_day: Optional[float] = Field(
        None, description="市内交通人均每天（元），由笔记里的票价折算；没查到就留空"
    )


def extract_price_hints(research: str, state: TravelAgentState) -> dict:
    """把调研笔记里的价格抽成结构化数字；抽取失败就返回空，预算会退回内置档位表"""
    if not research.strip():
        return {}

    llm = get_llm(temperature=0).with_structured_output(PriceHints)
    try:
        hints = llm.invoke(
            price_hints_prompt(hotel_preference=state["hotel_preference"], research=research)
        )
    except Exception as exc:
        print(f"[Master Agent] 价格抽取失败，退回内置档位估算：{type(exc).__name__}: {exc}")
        return {}

    return {key: value for key, value in hints.model_dump().items() if value not in (None, "")}


def collect_realtime_data(state: TravelAgentState, trip_days: int) -> str:
    """让模型自己调用工具联网查证真实价格，返回整理好的调研笔记"""
    print(f"[Master Agent] 调研阶段使用思考模型 {settings.DEEPSEEK_MODEL_THINKING}")
    llm = get_thinking_llm(temperature=0.2).bind_tools(RESEARCH_TOOLS)

    brief = "\n".join([
        f"目的地：{state['destination']}",
        f"日期：{state['start_date']} 至 {state['end_date']}（共 {trip_days} 天）",
        f"人数：{state['people_num']} 人",
        f"住宿偏好：{state['hotel_preference']}",
        f"交通方式：{state['traffic_type']}",
        f"游玩风格：{state['travel_style']}",
    ])

    messages = [
        SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
        HumanMessage(content=research_kickoff_prompt(brief)),
    ]

    for step in range(RESEARCH_MAX_STEPS):
        reply = llm.invoke(messages)
        messages.append(reply)
        calls = getattr(reply, "tool_calls", None) or []
        if not calls:
            print(f"[Master Agent] 调研阶段结束（第 {step + 1} 轮未再请求工具）")
            break

        for call in calls:
            name = call.get("name")
            args = call.get("args") or {}
            tool = RESEARCH_TOOL_MAP.get(name)
            print(f"[Master Agent] 调用工具 {name} {json.dumps(args, ensure_ascii=False)}")
            if tool is None:
                content = f"没有名为 {name} 的工具"
            else:
                try:
                    content = json.dumps(tool.invoke(args), ensure_ascii=False, default=str)
                except Exception as exc:
                    # 单个工具失败不中断调研，把错误回灌给模型
                    content = f"工具调用失败：{type(exc).__name__}: {exc}"
            messages.append(ToolMessage(content=content, tool_call_id=call.get("id")))
    else:
        print(f"[Master Agent] 调研阶段达到工具调用上限 {RESEARCH_MAX_STEPS} 轮")

    messages.append(HumanMessage(content=RESEARCH_SUMMARY_PROMPT))
    notes = get_thinking_llm(temperature=0).invoke(messages)
    return str(notes.content or "").strip()


def master_agent_node(state: TravelAgentState):
    print(f"[Master Agent] 开始处理任务 {state['task_id']}，目的地：{state['destination']}")

    # 1. 调用工具
    weather = query_weather.invoke({
        "destination": state["destination"],
        "start_date": state["start_date"],
        "end_date": state["end_date"],
    })
    start = date.fromisoformat(state["start_date"])
    end = date.fromisoformat(state["end_date"])
    trip_days = max((end - start).days + 1, 1)

    # 2. 让模型自己调工具联网查真实价格（失败则降级为无实时数据，不中断生成）
    research = ""
    try:
        research = collect_realtime_data(state, trip_days)
    except Exception as exc:
        print(f"[Master Agent] 实时数据调研失败，降级为无实时数据：{type(exc).__name__}: {exc}")

    research_text = research or "（本次未获取到实时数据：价格类字段请填 null，不要凭记忆编造）"

    # 3. 预算：优先采用调研到的真实价格，查不到才退回内置档位表
    price_hints = extract_price_hints(research, state)
    print(f"[Master Agent] 采用的真实价格：{price_hints or '（无，退回内置档位估算）'}")
    budget = calculate_budget.invoke({
        "total_budget": state["total_budget"],
        "people_num": state["people_num"],
        "days": trip_days,
        "hotel_preference": state["hotel_preference"],
        "traffic_type": state["traffic_type"],
        **price_hints,
    })

    # 4. RAG 检索
    rag_context = retrieve_knowledge(
        f"{state['destination']} 旅游攻略 必去景点 美食"
    )
    rag_text = (
        "\n".join(rag_context)
        if rag_context
        else "暂无本地知识库补充，请基于通用知识规划。"
    )

    # 5. 构建 Prompt 并调用 DeepSeek LLM
    partners = []
    if state.get("male_num"):
        partners.append(f"男{state['male_num']}人")
    if state.get("female_num"):
        partners.append(f"女{state['female_num']}人")
    people_suffix = "（" + "、".join(partners) + "）" if partners else ""
    people_desc = f"{state['people_num']}人{people_suffix}"

    budget_desc = (
        f"{state['total_budget']:.0f}元" if state.get("total_budget") else "未设置（不限制）"
    )
    budget_line = (
        f"总花费预估 {budget.get('total_cost')} 元（{budget.get('basis')}）；"
        f"{budget.get('suggestion')}"
    )
    if budget.get("upsell"):
        budget_line += f"\n    {budget.get('upsell')}——这只是备选档位提示，不计入上面的总花费。"

    # 重试时带上上次的评审意见，否则只是把同样的输入重跑一遍，改不出问题
    last_review = state.get("review_feedback") or []
    review_block = (
        "\n    【上次评审意见】（这次必须针对性修正）\n    "
        + "\n    ".join(last_review)
        + "\n"
        if last_review
        else ""
    )

    prompt = itinerary_prompt(
        destination=state["destination"],
        start_date=state["start_date"],
        end_date=state["end_date"],
        people_desc=people_desc,
        budget_desc=budget_desc,
        hotel_preference=state["hotel_preference"],
        travel_style=state["travel_style"],
        traffic_type=state["traffic_type"],
        extra_require=state["extra_require"],
        weather_summary=weather.get("summary", ""),
        budget_line=budget_line,
        research_text=research_text,
        rag_text=rag_text,
        review_block=review_block,
    )

    llm = get_llm(temperature=0.7)
    structured_llm = llm.with_structured_output(ItineraryOutput)

    try:
        print(f"[Master Agent] 正在调用 {settings.DEEPSEEK_MODEL} 生成结构化行程...")
        result = structured_llm.invoke(prompt)
        itinerary = result.model_dump()
    except Exception as e:
        print(f"[Master Agent] DeepSeek 生成失败，降级为默认模板: {e}")
        itinerary = {
            "destination": state["destination"],
            "days": [],
            "summary": "生成失败，请重试",
        }

    # 6. 预算按行程里选定的酒店/餐厅/交通/门票的实际花费重算；
    #    行程里查不到的项目才退回第 3 步的估算，第 3 步保留是因为提示词要用它引导规划
    budget_plan = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=state["people_num"],
        total_budget=state["total_budget"],
        fallback=budget,
        hotel_preference=state["hotel_preference"],
        traffic_type=state["traffic_type"],
    )
    print(f"[Master Agent] 预算按行程实际花费核算：{budget_plan['breakdown']}")

    return {
        "weather_data": weather,
        "research": research,
        "budget_plan": budget_plan,
        "itinerary": itinerary,
    }