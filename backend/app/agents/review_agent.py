import json
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.graph.state import TravelAgentState
from app.agents.prompts import REVIEW_SYSTEM_PROMPT, review_user_prompt
from app.llm.deepseek_client import get_llm

BUSY_SPOTS_PER_DAY = 5
OVER_BUDGET_PENALTY = 20
BUSY_DAY_PENALTY = 15

# 主观维度的权重：键必须与 prompts/review_prompts.py 里写明的那五个维度名一致
DIMENSION_WEIGHTS: Dict[str, float] = {
    "节奏": 0.25,
    "餐饮": 0.20,
    "交通": 0.20,
    "预算": 0.15,
    "偏好": 0.20,
}


class DimensionScore(BaseModel):
    """单个主观维度的打分：程序算不出来的那部分，交给评审模型"""

    name: str = Field(description="维度名，只能填这五个词之一：节奏 / 餐饮 / 交通 / 预算 / 偏好")
    score: int = Field(description="该维度 0-100 的整数分，要有区分度，不要五个维度都给同一个分")
    comment: str = Field(description="一句话说清为什么给这个分，不超过 40 字，要点到具体某一天")


class ReviewOutput(BaseModel):
    """评审模型的结构化输出：先写理由、再落分数，让模型先推理后打分"""

    summary: str = Field(description="一句话结论，不超过 30 字，会显示在评分下方")
    explanation: str = Field(
        description="评分解读，3-5 句话：先说整体优点，再指出主要风险，语气客观，不要写套话"
    )
    dimensions: List[DimensionScore] = Field(
        default_factory=list,
        description="五个维度各一条（节奏、餐饮、交通、预算、偏好），每条都要有分数和一句话理由",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="可执行的修改建议，每条写清改哪一天、改什么、改成什么，最多 5 条；"
        "没有可改的就返回空数组，不要写没有信息量的空话",
    )
    issues: List[str] = Field(
        default_factory=list,
        description="发现的客观问题，每条一句话并指明是第几天；没有具体问题就返回空数组",
    )
    needs_regeneration: bool = Field(
        description="是否必须重新生成行程。只有「重新排一次就能解决」的问题才填 true"
        "（如单日景点过多、同一天时间冲突、顺序导致来回折返）；"
        "超预算、天气差、查不到价格、用户没提的信息不完整，一律填 false"
    )


def _check_rules(state: TravelAgentState) -> Tuple[List[str], int, bool]:
    """规则预检：结果既作为客观证据喂给评审模型，也是模型调用失败时的降级评分。

    返回值里的 retryable 单独拎出来，是因为「值得让用户知道」和「值得重排一次」不是一回事：
    超预算只扣分、不触发重试——重排未必能把花费压进预算，却要多跑一轮生成。
    """
    notes: List[str] = []
    score = 100
    retryable = False

    budget_plan = state.get("budget_plan") or {}
    if budget_plan.get("is_over_budget"):
        notes.append(f"总花费超出预算（{budget_plan.get('suggestion')}）")
        score -= OVER_BUDGET_PENALTY

    itinerary = state.get("itinerary") or {}
    busy_days = [
        day
        for day in itinerary.get("days", [])
        if len(day.get("spots") or []) > BUSY_SPOTS_PER_DAY
    ]
    if busy_days:
        notes.append(
            f"有 {len(busy_days)} 天安排了超过 {BUSY_SPOTS_PER_DAY} 个景点，节奏偏紧"
        )
        score -= BUSY_DAY_PENALTY
        retryable = True

    # 距离合理性校验：实际项目中这里会调用高德地图距离计算

    return notes, score, retryable


def _weighted_score(dimensions: List[Dict[str, Any]]) -> Optional[int]:
    """把五个维度分加权成总分。

    模型漏给某个维度时直接不计该维度，并按剩下的权重归一化——否则缺项会被当成 0 分，
    一个只在餐饮上没说清楚的行程会被莫名扣掉 20 分。一个维度都没给就返回 None，
    交给调用方决定退到什么分。
    """
    total = 0.0
    total_weight = 0.0
    for item in dimensions or []:
        weight = DIMENSION_WEIGHTS.get(str(item.get("name") or "").strip())
        if weight is None:
            continue
        value = max(0.0, min(100.0, float(item.get("score") or 0)))
        total += weight * value
        total_weight += weight

    if total_weight <= 0:
        return None
    return int(round(total / total_weight))


def _build_review_prompt(state: TravelAgentState, rule_notes: List[str]) -> str:
    itinerary = state.get("itinerary") or {}
    budget_plan = state.get("budget_plan") or {}
    weather_data = state.get("weather_data") or {}
    days = itinerary.get("days") or []

    budget_desc = (
        f"{state['total_budget']:.0f}元" if state.get("total_budget") else "未设置（不限制）"
    )
    budget_line = (
        f"总花费预估 {budget_plan.get('total_cost')} 元（{budget_plan.get('basis')}）；"
        f"{budget_plan.get('suggestion')}"
        if budget_plan
        else "本次未核算预算"
    )
    rule_text = "\n".join(f"- {note}" for note in rule_notes) or "- 规则预检未发现问题"

    return review_user_prompt(
        destination=state["destination"],
        start_date=state["start_date"],
        end_date=state["end_date"],
        day_count=len(days),
        people_num=state["people_num"],
        budget_desc=budget_desc,
        hotel_preference=state["hotel_preference"],
        travel_style=state["travel_style"],
        traffic_type=state["traffic_type"],
        extra_require=state["extra_require"],
        weather_summary=weather_data.get("summary") or "本次未获取到天气信息",
        budget_line=budget_line,
        rule_text=rule_text,
        itinerary_json=json.dumps(itinerary, ensure_ascii=False),
    )


def review_agent_node(state: TravelAgentState):
    """行程评审 Agent：规则预检 + 大模型评审，分数与说明都由模型给出"""
    print(f"[Review Agent] 开始评审行程...")
    rule_notes, rule_score, rule_retryable = _check_rules(state)

    try:
        llm = get_llm(temperature=0).with_structured_output(ReviewOutput)
        review = llm.invoke([
            SystemMessage(content=REVIEW_SYSTEM_PROMPT),
            HumanMessage(content=_build_review_prompt(state, rule_notes)),
        ])
        report: Dict[str, Any] = review.model_dump()
    except Exception as exc:
        # 评审失败不该让整个任务失败：退回规则评分，此时的重试行为与旧版一致
        print(f"[Review Agent] 评审模型调用失败，退回规则评分：{type(exc).__name__}: {exc}")
        report = {
            "score": rule_score,
            "summary": "",
            "explanation": "",
            "dimensions": [],
            "suggestions": [],
            "issues": rule_notes,
            "needs_regeneration": rule_retryable,
        }

    report.setdefault("dimensions", [])
    report.setdefault("suggestions", [])

    # 总分由维度分加权算出，而不是让模型再报一个可能和自己维度分打架的总分；
    # 客观规则分（超预算、单日景点过多）作为上限——维度分打得再高，超支也不该拿满分
    weighted = _weighted_score(report["dimensions"])
    report["score"] = rule_score if weighted is None else min(weighted, rule_score)
    report["score"] = max(0, min(100, int(report["score"])))

    # review_feedback 的语义始终是「值得重排一次的意见」：模型说不用重排就留空，
    # 否则每次评审都会把 master 重跑一遍（含联网调研），白烧三次大模型调用
    feedback = list(report.get("issues") or []) if report.get("needs_regeneration") else []
    print(
        f"[Review Agent] 评审完成，评分 {report['score']}"
        f"（维度加权 {weighted if weighted is not None else '无'} / 规则 {rule_score}），"
        f"建议 {len(report['suggestions'])} 条，是否重排：{report['needs_regeneration']}"
    )

    return {
        "review_feedback": feedback,
        "review_score": report["score"],
        "review_report": report,
        "retry_count": state.get("retry_count", 0) + 1,
    }
