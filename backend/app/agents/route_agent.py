"""交通路线 Agent：按真实地理位置、开放时间与实时路况，把每天的景点重排成一条顺路的路线。

数据由高德提供（景点坐标、开放时间、两两通勤耗时、区域路况），排序决策交给「路线优化专家」提示词，
但**时间表与里程/耗时统计由代码算**：模型只给顺序、游玩时长和理由，不负责算数——
让它自己排时间，十有八九会排出「09:00 到故宫、08:40 到景山」这种倒挂的日程。

拿不到坐标时（没配高德 Key、境外目的地、景点名解析不出来）不硬排：
没有地理位置就无从谈「顺路」，保持主规划师的顺序，只记一条说明。
"""

import math
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.graph.state import TravelAgentState
from app.agents.prompts import ROUTE_EXPERT_PROMPT, route_day_prompt
from app.llm.deepseek_client import get_llm
from app.tools.map_route_tool import (
    DRIVING,
    WALKING,
    distance_matrix,
    resolve_spot,
    traffic_status,
)

DAY_START_MIN = 9 * 60            # 行程里没写到达时间时的默认出发时间
LATE_PENALTY_MIN = 600            # 赶不上闭馆的惩罚（分钟），用来把不可行的顺序顶掉
DEFAULT_DWELL_MIN = 120
MIN_DWELL_MIN = 30
MAX_DWELL_MIN = 360
DRIVE_SPEED_KMH = 25.0            # 只有高德没给这段耗时，才用直线距离按这个速度折算
WALK_SPEED_KMH = 4.8
CONGESTION_MIN_LEG_KM = 3.0       # 短途驾车耗时含起步停车，折算车速没意义，只统计 3 公里以上的路段
WEEKDAY_CN = "一二三四五六日"

_TIME_RE = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")
_HOURS_RE = re.compile(
    r"(\d{1,2})\s*[:：]\s*(\d{2})\s*[-–—~～至]\s*(\d{1,2})\s*[:：]\s*(\d{2})"
)
_CLOSED_RE = re.compile(r"周([一二三四五六日天])[^，,；;。]*?(?:关闭|闭馆|闭园|不开放|休息)")


class RouteStop(BaseModel):
    name: str = Field(description="景点名称，必须与【候选景点】里的名称完全一致")
    duration_minutes: int = Field(
        description=f"建议游玩时长（分钟），取值 {MIN_DWELL_MIN}-{MAX_DWELL_MIN}"
    )
    reason: str = Field(
        description="把它排在这个位置的理由，一句话，要说到具体依据"
        "（开放时间、地理顺路、路况、游玩节奏），不要写到达时间"
    )


class RouteDayOutput(BaseModel):
    order: List[RouteStop] = Field(
        description="重排后的景点顺序（从早到晚），必须包含全部候选景点且不重复"
    )
    advice: str = Field(
        description="一到两句提醒：路况、开放时间、需要提前预约等；没有就填空字符串"
    )


def _to_minutes(text) -> Optional[int]:
    """「09:00」「9:00」这类文本转成当天的分钟数"""
    match = _TIME_RE.search(str(text or ""))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _to_hhmm(minutes: float) -> str:
    value = max(0, int(round(minutes)))
    return f"{value // 60:02d}:{value % 60:02d}"


def _humanize(minutes: float) -> str:
    value = max(0, int(round(minutes)))
    if value < 60:
        return f"{value} 分钟"
    hours, rest = divmod(value, 60)
    return f"{hours} 小时 {rest} 分" if rest else f"{hours} 小时"


def parse_open_hours(text) -> Tuple[Optional[int], Optional[int], str]:
    """从高德的开放时间原文里取第一段营业时段与闭馆日。

    原文形如「旺季4月1日至10月31日 周二至周日 08:30-17:00 16:00停止检票，…，周一全天关闭」，
    第一段时段就是旺季营业时间；闭馆日单独返回，由调用方按当天是星期几判断。
    解析不出来就返回 (None, None, "")，表示不拿开放时间约束这个景点。
    """
    raw = str(text or "")
    match = _HOURS_RE.search(raw)
    open_min = close_min = None
    if match:
        open_min = int(match.group(1)) * 60 + int(match.group(2))
        close_min = int(match.group(3)) * 60 + int(match.group(4))
        if close_min <= open_min:  # 「20:00-02:00」这类跨天写法不当作闭馆时间
            close_min = None

    closed = "".join(dict.fromkeys(_CLOSED_RE.findall(raw)))  # 去重且保持出现顺序
    return open_min, close_min, closed


def _clamp_dwell(value) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DWELL_MIN
    return max(MIN_DWELL_MIN, min(MAX_DWELL_MIN, minutes))


def _straight_km(a: dict, b: dict) -> float:
    """两个坐标的球面直线距离（公里）；坐标缺失返回 0"""
    if a.get("lng") is None or b.get("lng") is None:
        return 0.0
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlng = math.radians(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371 * math.asin(min(1.0, math.sqrt(h)))


def _leg(matrix: Dict[Tuple[int, int], dict], i: int, j: int, points: List[dict], speed: float):
    """i→j 的耗时（分钟）与距离（公里）：优先用高德实测，缺了退回直线距离折算"""
    leg = matrix.get((i, j) if i < j else (j, i))
    if leg:
        return leg["minutes"], leg["km"]
    km = _straight_km(points[i], points[j])
    return km / speed * 60, km


def _schedule(
    order: List[int],
    points: List[dict],
    matrix: Dict[Tuple[int, int], dict],
    day_start: int,
    speed: float,
    reasons: Optional[Dict[int, str]] = None,
    dwells: Optional[Dict[int, int]] = None,
) -> dict:
    """按顺序排时间表：等开门、赶闭馆、算总通勤与总里程"""
    reasons = reasons or {}
    dwells = dwells or {}
    now = float(day_start)
    travel = wait = penalty = 0.0
    total_km = 0.0
    stops: List[dict] = []

    for position, index in enumerate(order):
        point = points[index]
        leg_minutes = leg_km = 0.0
        if position:
            leg_minutes, leg_km = _leg(matrix, order[position - 1], index, points, speed)
            now += leg_minutes
            travel += leg_minutes
            total_km += leg_km

        open_min, close_min = point.get("open_min"), point.get("close_min")
        waited = 0.0
        if open_min is not None and now < open_min:
            waited = open_min - now
            wait += waited
            now = open_min

        arrive = now
        dwell = dwells.get(index, point.get("dwell") or DEFAULT_DWELL_MIN)
        if close_min is not None and arrive + dwell > close_min:
            penalty += LATE_PENALTY_MIN  # 到得太晚，这个景点已经闭馆
        now += dwell

        stops.append({
            "index": index,
            "name": point["name"],
            "arrival_minutes": arrive,
            "arrival_time": _to_hhmm(arrive),
            "leave_time": _to_hhmm(now),
            "dwell": dwell,
            "travel_minutes": round(leg_minutes, 1),
            "distance_km": round(leg_km, 2),
            "reason": reasons.get(index, ""),
            "opentime": point.get("opentime") or "",
            "closed_note": point.get("closed") or "",
            "wait_minutes": round(waited, 1),
        })

    return {
        "stops": stops,
        "travel_minutes": round(travel, 1),
        "wait_minutes": round(wait, 1),
        "distance_km": round(total_km, 2),
        "penalty": penalty,
        "end_minutes": now,
    }


def _route_cost(plan: dict) -> float:
    return plan["travel_minutes"] + plan["wait_minutes"] + plan["penalty"]


def _two_opt(
    order: List[int],
    points: List[dict],
    matrix: Dict[Tuple[int, int], dict],
    day_start: int,
    speed: float,
) -> List[int]:
    """反转片段来缩短总成本；起点固定（首站往往是必须早去的那个）"""
    best = _route_cost(_schedule(order, points, matrix, day_start, speed))
    improved = True
    while improved:
        improved = False
        for i in range(1, len(order) - 1):
            for j in range(i + 1, len(order)):
                candidate = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                cost = _route_cost(_schedule(candidate, points, matrix, day_start, speed))
                if cost < best - 1e-9:
                    order, best, improved = candidate, cost, True
    return order


def optimize_order(
    points: List[dict],
    matrix: Dict[Tuple[int, int], dict],
    day_start: int,
    speed: float = DRIVE_SPEED_KMH,
) -> List[int]:
    """贪心最近邻 + 2-opt：每个景点都当一次起点试排，取总成本最低的一条开放路径。

    成本 = 通勤时间 + 等开门时间 + 赶不上闭馆的惩罚，所以开放时间天然参与排序：
    闭馆早的景点会被推到前面，而不是等模型记得这件事。
    """
    count = len(points)
    if count < 2:
        return list(range(count))

    best_order: Optional[List[int]] = None
    best_cost: Optional[float] = None
    for start in range(count):
        order = [start]
        remaining = [i for i in range(count) if i != start]
        while remaining:
            last = order[-1]
            nxt = min(
                remaining,
                key=lambda i: (_leg(matrix, last, i, points, speed)[0], i),
            )
            order.append(nxt)
            remaining.remove(nxt)

        order = _two_opt(order, points, matrix, day_start, speed)
        cost = _route_cost(_schedule(order, points, matrix, day_start, speed))
        if best_cost is None or cost < best_cost - 1e-9:
            best_order, best_cost = order, cost

    return best_order or list(range(count))


def _leg_lines(names: List[str], points: List[dict], drive: dict, walk: dict) -> str:
    """把两两通勤写成清单，比用中文对齐的表格更好读"""
    lines = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            drive_minutes, drive_km = _leg(drive, i, j, points, DRIVE_SPEED_KMH)
            walk_minutes, _ = _leg(walk, i, j, points, WALK_SPEED_KMH)
            marker = "" if (i, j) in drive else "（高德无数据，按直线距离折算）"
            lines.append(
                f"- {names[i]} ↔ {names[j]}：驾车 {drive_minutes:.0f} 分钟 / "
                f"{drive_km:.1f} 公里，步行 {walk_minutes:.0f} 分钟{marker}"
            )
    return "\n".join(lines)


def _congestion(points: List[dict], drive: dict) -> str:
    """路况：优先用高德交通态势，取不到就用驾车耗时折算平均车速（只统计 3 公里以上的路段）"""
    km = minutes = 0.0
    for leg in drive.values():
        if leg["km"] >= CONGESTION_MIN_LEG_KM:
            km += leg["km"]
            minutes += leg["minutes"]
    if km <= 0 or minutes <= 0:
        return ""
    speed = km / (minutes / 60)
    if speed >= 22:
        label = "畅通"
    elif speed >= 15:
        label = "缓行"
    else:
        label = "拥堵"
    return f"{label}（当天路段平均车速约 {speed:.0f} 公里/小时，按高德驾车耗时与距离折算）"


def _build_prompt(
    state: TravelAgentState,
    day: dict,
    date_text: str,
    points: List[dict],
    drive: dict,
    walk: dict,
    day_start: int,
    congestion: str,
    traffic: Optional[dict],
) -> str:
    names = [point["name"] for point in points]
    weekday = ""
    try:
        weekday = "周" + WEEKDAY_CN[date.fromisoformat(date_text).weekday()]
    except (TypeError, ValueError):
        weekday = ""

    closed_notes = [
        f"{point['name']}：{'、'.join('周' + day for day in point['closed'])}"
        for point in points
        if point.get("closed")
    ]

    spot_lines = []
    for position, point in enumerate(points, start=1):
        spot_lines.append(
            f"{position}. {point['name']}\n"
            f"   坐标：{point['lng']:.6f},{point['lat']:.6f}\n"
            f"   开放时间：{point['opentime'] or '未查到，按常规白天开放处理'}\n"
            f"   主规划师建议游玩：{point['dwell']} 分钟"
            + (f"\n   门票：{point['ticket']} 元/人" if point.get("ticket") is not None else "")
        )

    traffic_text = traffic.get("description") if traffic else ""
    if traffic and traffic.get("roads"):
        road_text = "、".join(
            f"{road['name']}（{road['status']}）" for road in traffic["roads"] if road.get("name")
        )
        if road_text:
            traffic_text = f"{traffic_text}；主要路段：{road_text}"

    return route_day_prompt(
        day_number=day.get("day"),
        date_text=date_text,
        weekday=weekday,
        destination=state.get("destination"),
        traffic_type=state.get("traffic_type"),
        travel_style=state.get("travel_style"),
        start_time=_to_hhmm(day_start),
        original_order=" → ".join(names),
        closed_note=("需要注意的闭馆安排：" + "；".join(closed_notes)) if closed_notes else "",
        spot_lines=chr(10).join(spot_lines),
        leg_lines=_leg_lines(names, points, drive, walk),
        traffic_text=traffic_text or congestion or "未获取到路况数据",
        dwell_range=f"{MIN_DWELL_MIN}-{MAX_DWELL_MIN}",
        point_count=len(points),
    )


def _ask_expert(prompt: str) -> Optional[RouteDayOutput]:
    try:
        llm = get_llm(temperature=0.3).with_structured_output(RouteDayOutput)
        return llm.invoke([
            SystemMessage(content=ROUTE_EXPERT_PROMPT),
            HumanMessage(content=prompt),
        ])
    except Exception as exc:
        print(f"[Route Agent] 路线优化模型调用失败，改用代码算出的顺序：{type(exc).__name__}: {exc}")
        return None


def _apply_llm_order(result: Optional[RouteDayOutput], points: List[dict]) -> Optional[dict]:
    """把模型给的名称顺序映射回下标；漏景点、多景点、名字对不上都返回 None"""
    if result is None or not result.order:
        return None

    remaining: Dict[str, List[int]] = {}
    for index, point in enumerate(points):
        remaining.setdefault(point["name"], []).append(index)

    order: List[int] = []
    dwells: Dict[int, int] = {}
    reasons: Dict[int, str] = {}
    for stop in result.order:
        name = str(stop.name or "").strip()
        if not remaining.get(name):
            return None
        index = remaining[name].pop(0)
        order.append(index)
        dwells[index] = _clamp_dwell(stop.duration_minutes)
        reasons[index] = str(stop.reason or "").strip()

    if len(order) != len(points):
        return None
    return {"order": order, "dwells": dwells, "reasons": reasons, "advice": str(result.advice or "").strip()}


def _summarize(plan: dict, ordered_names: List[str]) -> str:
    text = (
        f"{' → '.join(ordered_names)}；全程 {plan['distance_km']:.1f} 公里，"
        f"路上约 {_humanize(plan['travel_minutes'])}，"
        f"{plan['stops'][0]['arrival_time']}-{_to_hhmm(plan['end_minutes'])}"
    )
    if plan["wait_minutes"] >= 10:
        text += f"（含等开门 {_humanize(plan['wait_minutes'])}）"
    return text


def optimize_day(
    day: dict,
    day_index: int,
    state: TravelAgentState,
    override: str,
) -> Optional[dict]:
    """优化一天的路线并写回 itinerary；返回这一天的小结，跳过时返回 None"""
    spots = [spot for spot in (day.get("spots") or []) if str(spot.get("name") or "").strip()]
    if override:
        day["transport"] = override
    if len(spots) < 2:
        return None

    city = state.get("destination") or ""
    resolved = [resolve_spot(spot["name"], city) for spot in spots]
    if any(item is None for item in resolved):
        missing = "、".join(
            spot["name"] for spot, item in zip(spots, resolved) if item is None
        )
        print(f"[Route Agent] 第 {day_index + 1} 天有景点解析不到坐标（{missing}），保持原顺序")
        day["route"] = {
            "optimized": False,
            "note": f"未取到「{missing}」的坐标，无法计算顺路路线，保持主规划师的顺序",
        }
        return None

    points = []
    for spot, item in zip(spots, resolved):
        # 开放时间优先用高德的，高德没返回就用主规划师从调研笔记里写下的
        opentime = item.get("opentime") or spot.get("opentime") or ""
        open_min, close_min, closed = parse_open_hours(opentime)
        points.append({
            "name": spot["name"],
            "lng": item["lng"],
            "lat": item["lat"],
            "opentime": opentime,
            "open_min": open_min,
            "close_min": close_min,
            "closed": closed,
            "dwell": _clamp_dwell(spot.get("duration_minutes")),
            "ticket": spot.get("ticket"),
        })

    starts = [value for value in (_to_minutes(spot.get("start_time")) for spot in spots) if value]
    day_start = min(starts) if starts else DAY_START_MIN

    drive = distance_matrix(points, DRIVING)
    walk = distance_matrix(points, WALKING)
    traffic = traffic_status(points)
    congestion = _congestion(points, drive)

    fallback_order = optimize_order(points, drive, day_start)
    fallback_plan = _schedule(fallback_order, points, drive, day_start, DRIVE_SPEED_KMH)

    date_text = str(day.get("date") or "")
    if not date_text:
        try:
            date_text = (
                date.fromisoformat(state["start_date"]) + timedelta(days=day_index)
            ).isoformat()
        except (KeyError, TypeError, ValueError):
            date_text = ""

    expert = _ask_expert(
        _build_prompt(state, day, date_text, points, drive, walk, day_start, congestion, traffic)
    )
    llm_plan = _apply_llm_order(expert, points)

    plan = fallback_plan
    order = fallback_order
    dwells: Dict[int, int] = {}
    reasons: Dict[int, str] = {}
    advice = ""
    # 高德两两耗时没取到时，排序用的是直线距离折算，来源如实标注，别冒充路径规划
    map_label = "高德路径规划" if drive else "直线距离折算"
    source = f"{map_label} + 路线优化模型"

    if llm_plan:
        llm_plan_full = _schedule(
            llm_plan["order"], points, drive, day_start, DRIVE_SPEED_KMH,
            llm_plan["reasons"], llm_plan["dwells"],
        )
        # 模型排的顺序如果会让某个景点赶不上闭馆，而代码算的顺序不会，就用代码的
        if llm_plan_full["penalty"] > fallback_plan["penalty"]:
            print(
                f"[Route Agent] 模型给的顺序会赶不上闭馆"
                f"（{llm_plan_full['penalty']:.0f} > {fallback_plan['penalty']:.0f}），"
                f"改用代码算的顺序"
            )
        else:
            plan, order = llm_plan_full, llm_plan["order"]
            dwells, reasons = llm_plan["dwells"], llm_plan["reasons"]
            advice = llm_plan["advice"]
            if order != fallback_order:
                print(
                    f"[Route Agent] 采用模型的顺序：{order}（代码算的：{fallback_order}，"
                    f"通勤 {plan['travel_minutes']:.0f} 分钟）"
                )
    else:
        source = map_label

    ordered_names = [points[index]["name"] for index in order]
    original_names = [spot["name"] for spot in spots]
    day["spots"] = [
        {
            **spots[stop["index"]],
            "start_time": stop["arrival_time"],
            "duration_minutes": stop["dwell"],
        }
        for stop in plan["stops"]
    ]
    day["route_optimized"] = True
    day["route"] = {
        "optimized": True,
        "summary": _summarize(plan, ordered_names),
        "advice": advice,
        "congestion": congestion,
        "total_distance_km": plan["distance_km"],
        "total_travel_minutes": plan["travel_minutes"],
        "total_wait_minutes": plan["wait_minutes"],
        "start_time": plan["stops"][0]["arrival_time"],
        "end_time": _to_hhmm(plan["end_minutes"]),
        "reordered": ordered_names != original_names,
        "source": source,
        "stops": [
            {
                "name": stop["name"],
                "arrival_time": stop["arrival_time"],
                "leave_time": stop["leave_time"],
                "duration_minutes": stop["dwell"],
                "travel_minutes": stop["travel_minutes"],
                "distance_km": stop["distance_km"],
                "opentime": stop["opentime"],
                "reason": stop["reason"] or "",
            }
            for stop in plan["stops"]
        ],
    }
    print(
        f"[Route Agent] 第 {day_index + 1} 天路线：{day['route']['summary']}"
        + (f"；{advice}" if advice else "")
    )

    return {
        "day": day.get("day") or day_index + 1,
        "summary": day["route"]["summary"],
        "advice": advice,
        "congestion": congestion,
        "total_distance_km": plan["distance_km"],
        "total_travel_minutes": plan["travel_minutes"],
        "reordered": day["route"]["reordered"],
        "source": source,
    }


def route_agent_node(state: TravelAgentState):
    """交通路线 Agent：按地理位置、开放时间与路况重排每天的景点顺序"""
    print("[Route Agent] 正在优化路线...")

    # 「不限」和多选值都不能代表某一天的交通方式，这时保留模型为每天排的具体交通
    traffic_type = state.get("traffic_type") or ""
    override = (
        traffic_type
        if traffic_type and traffic_type != "不限" and "、" not in traffic_type
        else ""
    )

    itinerary = state.get("itinerary") or {}
    days = itinerary.get("days") or []
    if not days:
        return {"route_plan": {"optimized": False, "reason": "行程为空", "days": []}}

    plans: List[dict] = []
    for index, day in enumerate(days):
        try:
            plan = optimize_day(day, index, state, override)
        except Exception as exc:
            # 路线优化失败不该让整份行程失败：保留原顺序，只记说明
            print(f"[Route Agent] 第 {index + 1} 天路线优化失败：{type(exc).__name__}: {exc}")
            day["route"] = {"optimized": False, "note": f"路线优化失败（{type(exc).__name__}）"}
            plan = None
        if plan:
            plans.append(plan)

    print(f"[Route Agent] 优化完成，{len(plans)}/{len(days)} 天重排了路线")
    return {
        "route_plan": {"optimized": bool(plans), "days": plans},
        "itinerary": itinerary,  # 顺序与时间已就地改好，显式回写，别依赖对象引用
    }
