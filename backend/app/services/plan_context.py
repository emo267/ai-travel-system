"""把用户关联的行程整理成一段文本，供对话助手在回答前阅读。

以前助手只是把 task_id 存进聊天记录，从没读过行程内容，所以「关联行程」等于摆设：
用户问「第三天住哪儿」，助手还是去联网搜。这里负责按归属取出行程，
并把它压成模型能直接读的要点（每天的景点/餐饮/住宿/交通 + 总结 + 预算）。
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.travel_plan import TravelPlan
from app.db.models.travel_task import TravelTask
from app.services import travel_service

# 每天的文字说明动辄两三百字，几天叠加会把景点、价格这些要点淹掉，只取开头一段
DESC_LIMIT = 160
SUMMARY_LIMIT = 400
EXTRA_LIMIT = 100


def load_linked_plan(
    db: Session,
    user_id: int,
    task_id: Optional[int],
) -> tuple[Optional[TravelTask], Optional[TravelPlan]]:
    """按归属取关联行程。

    没关联、task_id 非法、行程不属于当前用户、或已被删除，都返回 (None, None)：
    关联行程只是回答的补充材料，取不到就不注入，对话本身照常进行。
    注意 task_id 来自客户端，必须先过归属校验再取方案，否则别人的行程会被读出来。
    """
    if not task_id:
        return None, None
    task = travel_service.get_travel_task(db, user_id, int(task_id))
    if not task:
        return None, None
    return task, travel_service.get_travel_plan_by_task(db, task.task_id)


def plan_label(task: TravelTask) -> str:
    return f"{task.destination} · {task.start_date} 至 {task.end_date}"


def _num(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value) -> str:
    return f"{_num(value):,.0f}" if _num(value) is not None else ""


def _trim(text, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _spot_line(spot: dict) -> str:
    name = str(spot.get("name") or "未命名景点")
    bits = []
    if spot.get("start_time"):
        bits.append(str(spot["start_time"]))
    minutes = _num(spot.get("duration_minutes"))
    if minutes:
        bits.append(f"{minutes:.0f} 分钟")
    ticket = _num(spot.get("ticket"))
    if ticket is None:
        bits.append("门票待确认")
    elif ticket == 0:
        bits.append("免费")
    else:
        bits.append(f"门票 {_money(ticket)} 元/人")
    return f"{name}（{'，'.join(bits)}）" if bits else name


def _meal_line(meal: dict) -> str:
    name = str(meal.get("name") or "未命名餐饮")
    cost = _num(meal.get("cost"))
    return f"{name}（人均待确认）" if cost is None else f"{name}（人均 {_money(cost)} 元）"


def _basic_line(task: TravelTask) -> str:
    parts = [
        f"目的地：{task.destination}",
        f"日期：{task.start_date} 至 {task.end_date}",
        f"人数：{task.people_num} 人",
    ]
    total = _num(task.total_budget)
    parts.append(f"预算：{_money(total)} 元" if total else "预算：未设置")
    if task.hotel_preference:
        parts.append(f"住宿偏好：{task.hotel_preference}")
    if task.traffic_type:
        parts.append(f"交通方式：{task.traffic_type}")
    if task.travel_style:
        parts.append(f"游玩风格：{task.travel_style}")
    if task.extra_require:
        parts.append(f"额外需求：{_trim(task.extra_require, EXTRA_LIMIT)}")
    return "【行程基本信息】" + "；".join(parts)


def _budget_line(plan: TravelPlan, budget: dict) -> Optional[str]:
    breakdown = budget.get("breakdown") or {}
    labels = (("hotel", "住宿"), ("food", "餐饮"), ("transport", "交通"), ("ticket", "门票"))
    items = "、".join(
        f"{label} {_money(breakdown[key])} 元"
        for key, label in labels
        if _num(breakdown.get(key)) is not None
    )
    if not items:
        return None
    total = _num(plan.total_cost)
    head = f"【预算】总花费 {_money(total)} 元（{items}）" if total is not None else f"【预算】{items}"
    if budget.get("basis"):
        head += f"\n  预算口径：{_trim(budget['basis'], 300)}"
    return head


def build_plan_brief(task: TravelTask, plan: Optional[TravelPlan]) -> str:
    """把行程压成要点文本；行程还没生成完时明确说出来，免得助手凭空编一份"""
    lines = [_basic_line(task)]

    itinerary = (plan.itinerary if plan else None) or {}
    days = [day for day in (itinerary.get("days") or []) if isinstance(day, dict)]
    if not days:
        lines.append(
            "【行程内容】这份行程还没有生成出每日安排（可能仍在生成中或已生成失败），"
            "现在只能依据上面的基本信息回答，并提醒用户等行程生成完成后再问细节。"
        )
        return "\n".join(lines)

    for index, day in enumerate(days, start=1):
        head = f"第 {day.get('day') or index} 天"
        if day.get("date"):
            head += f"（{day['date']}）"
        lines.append(head)

        spots = [spot for spot in (day.get("spots") or []) if isinstance(spot, dict)]
        if spots:
            lines.append("  景点：" + " → ".join(_spot_line(spot) for spot in spots))

        meals = [meal for meal in (day.get("meals") or []) if isinstance(meal, dict)]
        if meals:
            lines.append("  餐饮：" + "、".join(_meal_line(meal) for meal in meals))

        if day.get("hotel"):
            hotel = str(day["hotel"])
            price = _num(day.get("hotel_price"))
            if price:
                hotel += f"（{_money(price)} 元/间/晚）"
            lines.append(f"  住宿：{hotel}")

        if day.get("transport"):
            transport = str(day["transport"])
            cost = _num(day.get("transport_cost"))
            if cost is not None:
                transport += f"（人均 {_money(cost)} 元/天）"
            lines.append(f"  交通：{transport}")

        if day.get("description"):
            lines.append(f"  当天说明：{_trim(day['description'], DESC_LIMIT)}")

    if itinerary.get("summary"):
        lines.append(f"【行程总结】{_trim(itinerary['summary'], SUMMARY_LIMIT)}")

    if plan is not None:
        budget_line = _budget_line(plan, itinerary.get("budget") or {})
        if budget_line:
            lines.append(budget_line)
        if plan.weather_summary:
            lines.append(f"【天气】{_trim(plan.weather_summary, 200)}")

    review = itinerary.get("review") or {}
    if review.get("summary"):
        lines.append(f"【行程评审】{_trim(review['summary'], 200)}")

    return "\n".join(lines)
