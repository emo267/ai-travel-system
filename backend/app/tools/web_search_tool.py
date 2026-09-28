import httpx
from langchain_core.tools import tool

from app.core.config import settings

TAVILY_ENDPOINT = "https://api.tavily.com/search"
TIMEOUT_SECONDS = 20
MAX_RESULTS = 5
SNIPPET_LIMIT = 400


def _format_results(payload: dict) -> str:
    lines = []

    answer = (payload.get("answer") or "").strip()
    if answer:
        lines.append(f"摘要：{answer}")

    for index, item in enumerate(payload.get("results") or [], start=1):
        title = (item.get("title") or "").strip()
        content = " ".join((item.get("content") or "").split())
        if len(content) > SNIPPET_LIMIT:
            content = content[:SNIPPET_LIMIT] + "…"
        url = (item.get("url") or "").strip()
        lines.append(f"{index}. {title}：{content}（{url}）")

    return "\n".join(lines)


@tool
def web_search(query: str) -> str:
    """联网搜索目的地的实时攻略、景点、美食与交通信息"""
    if not settings.TAVILY_API_KEY:
        return "未配置 Tavily API Key，联网搜索不可用，请基于通用知识规划。"

    try:
        response = httpx.post(
            TAVILY_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}"},
            json={
                "query": query,
                "max_results": MAX_RESULTS,
                "search_depth": "basic",
                "include_answer": True,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        # 搜索是锦上添花，失败时降级为通用知识，不能让整个行程生成跟着失败
        print(f"[Web Search] Tavily 调用失败，降级处理：{type(exc).__name__}: {exc}")
        return "联网搜索暂不可用，请基于通用知识规划。"

    text = _format_results(response.json())
    return text or "联网搜索未返回有效结果，请基于通用知识规划。"
