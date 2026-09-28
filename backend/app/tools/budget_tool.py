import re
from math import ceil
from typing import Optional

from langchain_core.tools import tool

# 元/间/晚。青年旅舍现实中按床位计价，这里折算成"同等房价"以便与其他档位统一比较
HOTEL_PRICES = {
    "青年旅舍": 120,
    "民宿/客栈": 200,
    "经济型酒店": 250,
    "中档型酒店": 420,
    "豪华型酒店": 800,
}
HOTEL_DEFAULT = "经济型酒店"

# 元/人/天
TRAFFIC_PRICES = {
    "步行": 0,
    "骑行": 10,
    "公共交通": 30,
    "网约车": 120,
    "自驾": 150,
}
TRAFFIC_DEFAULT = "公共交通"

FOOD_PER_PERSON_PER_DAY = 150
TICKET_PER_PERSON_PER_DAY = 80

UNLIMITED = "不限"
NO_HOTEL = "不安排住宿"
SEPARATOR = "、"

# 表单改版前的旧值
HOTEL_ALIASES = {"经济型": "经济型酒店", "轻奢": "中档型酒店", "豪华": "豪华型酒店"}


def _money(value: float) -> str:
    return f"{value:,.0f}"


def _split(value) -> list[str]:
    return [part.strip() for part in str(value or "").split(SEPARATOR) if part.strip()]


def _hotel_plan(selection: str) -> dict:
    """住宿档位解析：多选时取最低档计入预算，其余档位留给调用方做对比提示"""
    parts = _split(selection)

    if not parts or NO_HOTEL in parts:
        return {"mode": "none", "price": 0, "tier": NO_HOTEL, "others": []}

    if parts == [UNLIMITED]:
        return {
            "mode": "unlimited",
            "price": HOTEL_PRICES[HOTEL_DEFAULT],
            "tier": HOTEL_DEFAULT,
            "others": [],
        }

    tiers = [HOTEL_ALIASES.get(part, part) for part in parts if part != UNLIMITED]
    tiers = sorted({tier for tier in tiers if tier in HOTEL_PRICES}, key=HOTEL_PRICES.get)
    if not tiers:
        tiers = [HOTEL_DEFAULT]

    cheapest, *rest = tiers
    return {
        "mode": "tier",
        "price": HOTEL_PRICES[cheapest],
        "tier": cheapest,
        "others": [(tier, HOTEL_PRICES[tier]) for tier in rest],
    }


def _traffic_plan(selection: str) -> tuple[int, str]:
    parts = [part for part in _split(selection) if part != UNLIMITED]
    options = sorted(
        ((TRAFFIC_PRICES[part], part) for part in parts if part in TRAFFIC_PRICES),
    )
    if not options:
        return TRAFFIC_PRICES[TRAFFIC_DEFAULT], TRAFFIC_DEFAULT
    return options[0]


def _settle(total_cost: float, total_budget) -> tuple[Optional[float], bool, str]:
    """超支判断与结论文案，两套核算口径（档位估算 / 行程实际花费）共用"""
    budget = None
    if total_budget is not None:
        try:
            value = float(total_budget)
            budget = value if value > 0 else None
        except (TypeError, ValueError):
            budget = None

    is_over_budget = budget is not None and total_cost > budget

    if budget is None:
        suggestion = "未设置预算，不做超支判断"
    elif is_over_budget:
        suggestion = (
            f"超出预算 ¥{_money(total_cost - budget)}，建议降低住宿档位或减少付费景点"
        )
    else:
        suggestion = f"预算充足，预计结余 ¥{_money(budget - total_cost)}"

    return budget, is_over_budget, suggestion


@tool
def calculate_budget(
    total_budget: Optional[float],
    people_num: int,
    days: int,
    hotel_preference: str = "",
    traffic_type: str = "",
    hotel_price_per_room_night: Optional[float] = None,
    hotel_price_text: str = "",
    meal_per_person_per_day: Optional[float] = None,
    transit_per_person_per_day: Optional[float] = None,
) -> dict:
    """核算旅行预算：优先采用联网查到的真实价格，查不到时退回内置档位估算"""
    people = max(int(people_num or 1), 1)
    trip_days = max(int(days or 1), 1)
    nights = max(trip_days - 1, 1)
    rooms = ceil(people / 2)

    hotel = _hotel_plan(hotel_preference)
    traffic_price, traffic_tier = _traffic_plan(traffic_type)

    # 联网查到的价格优先于内置档位表；「不安排住宿」仍然忽略房价
    web_hotel_price = None
    if hotel["mode"] != "none" and hotel_price_per_room_night:
        try:
            value = float(hotel_price_per_room_night)
            web_hotel_price = value if value > 0 else None
        except (TypeError, ValueError):
            web_hotel_price = None

    hotel_unit = web_hotel_price if web_hotel_price else hotel["price"]
    food_unit = float(meal_per_person_per_day) if meal_per_person_per_day else FOOD_PER_PERSON_PER_DAY
    transport_unit = (
        float(transit_per_person_per_day) if transit_per_person_per_day else traffic_price
    )

    hotel_cost = hotel_unit * rooms * nights
    food_cost = food_unit * people * trip_days
    transport_cost = transport_unit * people * trip_days
    ticket_cost = TICKET_PER_PERSON_PER_DAY * people * trip_days
    total_cost = hotel_cost + food_cost + transport_cost + ticket_cost

    if hotel["mode"] == "none":
        hotel_basis = "未安排住宿，不计住宿费"
    elif web_hotel_price:
        shown = hotel_price_text.strip() or f"{_money(web_hotel_price)} 元/间/晚"
        hotel_basis = (
            f"住宿按联网查到的「{shown}」取中位 {_money(web_hotel_price)} 元/间/晚"
            f" × {rooms} 间 × {nights} 晚计"
        )
    elif hotel["mode"] == "unlimited":
        hotel_basis = f"住宿档位不限，按「{hotel['tier']}」{hotel['price']} 元/间/晚估算"
    else:
        hotel_basis = (
            f"住宿按「{hotel['tier']}」{hotel['price']} 元/间/晚"
            f" × {rooms} 间 × {nights} 晚计"
        )

    food_basis = (
        f"餐饮按联网查到的人均 {_money(food_unit)} 元/人/天"
        if meal_per_person_per_day
        else f"餐饮按 {_money(food_unit)} 元/人/天估算"
    )
    transport_basis = (
        f"交通按联网查到的人均 {_money(transport_unit)} 元/人/天"
        if transit_per_person_per_day
        else f"交通按「{traffic_tier}」{_money(transport_unit)} 元/人/天计"
    )
    basis = f"{hotel_basis}；{food_basis}；{transport_basis}；门票按 {TICKET_PER_PERSON_PER_DAY} 元/人/天估算"

    # 升级对比只在"按内置档位估算"时有意义；用了真实房价就没得比
    upsell = ""
    if hotel["others"] and not web_hotel_price:
        upsell = "若住宿升级：" + "；".join(
            f"「{tier}」（{price} 元/间/晚）需再加 ¥{_money((price - hotel['price']) * rooms * nights)}"
            f"，总计 ¥{_money(total_cost + (price - hotel['price']) * rooms * nights)}"
            for tier, price in hotel["others"]
        )

    budget, is_over_budget, suggestion = _settle(total_cost, total_budget)

    return {
        "total_cost": total_cost,
        "breakdown": {
            "hotel": hotel_cost,
            "food": food_cost,
            "transport": transport_cost,
            "ticket": ticket_cost,
        },
        "is_over_budget": is_over_budget,
        "total_budget": budget,
        "nights": nights,
        "rooms": rooms,
        "basis": basis,
        "upsell": upsell,
        "suggestion": suggestion,
    }


# day.hotel 里写的是「如家（王府井店），约 480 元/晚」这类房价文字，
# hotel_price 缺失时用它兜底；只在明确写了「元」时才认，避免把「地铁 1 号线」当成价格
_RANGE_MONEY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|—|~|～|至)\s*(\d+(?:\.\d+)?)\s*元")
_SINGLE_MONEY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*元")


def _price_from_text(text) -> Optional[float]:
    """从住宿文字里取房价：区间取中位，单值取该值；没写「元」就返回 None"""
    if not text:
        return None
    match = _RANGE_MONEY_RE.search(str(text))
    if match:
        return (float(match.group(1)) + float(match.group(2))) / 2
    match = _SINGLE_MONEY_RE.search(str(text))
    return float(match.group(1)) if match else None


def _amount(value) -> Optional[float]:
    """把行程里的价格转成数字；空值或非法值都算「没查到」"""
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _middle(values: list) -> float:
    """取行程里真实出现过的价格（偶数个时取中间偏小的那个），不用平均值编出一个没出现过的价"""
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def calculate_budget_from_itinerary(
    itinerary: Optional[dict],
    people_num: int,
    total_budget: Optional[float] = None,
    fallback: Optional[dict] = None,
    hotel_preference: str = "",
    traffic_type: str = "",
) -> dict:
    """按行程详情里的实际花费核算预算。

    住宿取行程所选酒店的房价、餐饮取推荐餐厅的人均、交通取当天实际花费、门票取各景点票价；
    行程里确实没有价格的项目，才退回 fallback（生成前按联网价/档位算的估算）里的对应项。
    返回结构与 calculate_budget 一致，详情页与评审逻辑不用改。
    """
    people = max(int(people_num or 1), 1)
    days = (itinerary or {}).get("days") or []
    trip_days = max(len(days), 1)
    nights = max(trip_days - 1, 1)
    rooms = ceil(people / 2)
    estimate = (fallback or {}).get("breakdown") or {}

    tickets: list = []
    meals: list = []
    hotels: list = []
    transports: list = []
    unpriced_spots = 0
    unpriced_meals = 0

    for day in days:
        if not isinstance(day, dict):
            continue
        for spot in day.get("spots") or []:
            price = _amount((spot or {}).get("ticket"))
            if price is None:
                unpriced_spots += 1
            else:
                tickets.append(price)
        for meal in day.get("meals") or []:
            price = _amount((meal or {}).get("cost"))
            if price is None:
                unpriced_meals += 1
            else:
                meals.append(price)
        price = _amount(day.get("hotel_price"))
        if price is None:
            price = _price_from_text(day.get("hotel"))
        if price is not None:
            hotels.append(price)
        # 交通只认结构化字段：day.transport 的文字是票价（起步价/单程），
        # 不是当天总花费，按它算会系统性偏低（实测把「单程 4—6 元」当成了一天的交通费）
        price = _amount(day.get("transport_cost"))
        if price is not None:
            transports.append(price)

    hotel = _hotel_plan(hotel_preference)
    if hotel["mode"] == "none":
        hotel_cost = 0
        hotel_basis = "未安排住宿，不计住宿费"
    elif hotels:
        hotel_unit = _middle(hotels)
        hotel_cost = hotel_unit * rooms * nights
        hotel_basis = (
            f"住宿按行程所选酒店的 {_money(hotel_unit)} 元/间/晚"
            f" × {rooms} 间 × {nights} 晚计"
        )
    else:
        hotel_cost = estimate.get("hotel", hotel["price"] * rooms * nights)
        hotel_basis = (
            f"住宿：行程内未查到房价，按「{hotel['tier']}」{hotel['price']} 元/间/晚估算"
        )

    if meals:
        food_unit = sum(meals)
        food_cost = food_unit * people
        food_basis = f"餐饮按行程内 {len(meals)} 餐的实际人均合计 {_money(food_unit)} 元/人"
        if unpriced_meals:
            food_basis += f"（另有 {unpriced_meals} 餐未查到人均，未计入）"
    else:
        food_cost = estimate.get("food", FOOD_PER_PERSON_PER_DAY * people * trip_days)
        food_basis = f"餐饮：行程内未查到人均，按 {FOOD_PER_PERSON_PER_DAY} 元/人/天估算"

    if transports:
        transport_unit = sum(transports)
        transport_cost = transport_unit * people
        transport_basis = f"交通按行程内实际人均合计 {_money(transport_unit)} 元/人"
    else:
        traffic_price, traffic_tier = _traffic_plan(traffic_type)
        transport_cost = estimate.get("transport", traffic_price * people * trip_days)
        transport_basis = (
            f"交通：行程内未查到实际花费，"
            f"按「{traffic_tier}」{_money(traffic_price)} 元/人/天计"
        )

    if tickets:
        ticket_unit = sum(tickets)
        ticket_cost = ticket_unit * people
        ticket_basis = f"门票按行程内 {len(tickets)} 个景点的实际票价合计 {_money(ticket_unit)} 元/人"
        if unpriced_spots:
            ticket_basis += f"（另有 {unpriced_spots} 个景点未查到票价，未计入）"
    else:
        ticket_cost = estimate.get("ticket", TICKET_PER_PERSON_PER_DAY * people * trip_days)
        ticket_basis = f"门票：行程内未查到票价，按 {TICKET_PER_PERSON_PER_DAY} 元/人/天估算"

    total_cost = hotel_cost + food_cost + transport_cost + ticket_cost
    basis = "；".join([hotel_basis, food_basis, transport_basis, ticket_basis])

    # 用行程里的真实房价时，没有「升级档位对比」可言，只保留档位估算时的对比
    upsell = "" if hotels or hotel["mode"] == "none" else (fallback or {}).get("upsell", "")

    budget, is_over_budget, suggestion = _settle(total_cost, total_budget)

    return {
        "total_cost": total_cost,
        "breakdown": {
            "hotel": hotel_cost,
            "food": food_cost,
            "transport": transport_cost,
            "ticket": ticket_cost,
        },
        "is_over_budget": is_over_budget,
        "total_budget": budget,
        "nights": nights,
        "rooms": rooms,
        "basis": basis,
        "upsell": upsell,
        "suggestion": suggestion,
    }
