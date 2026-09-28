"""预算必须按行程详情里选定的酒店/餐厅/交通/门票实际花费核算，而不是代码里的固定档位价。"""

import pytest

from app.tools.budget_tool import calculate_budget, calculate_budget_from_itinerary


def _estimate(people_num=2, days=3, hotel_preference="经济型酒店", traffic_type="公共交通"):
    """生成前的档位估算，作为「行程里查不到价格」时的兜底基准"""
    return calculate_budget.invoke({
        "total_budget": None,
        "people_num": people_num,
        "days": days,
        "hotel_preference": hotel_preference,
        "traffic_type": traffic_type,
    })


def _day(**kwargs):
    day = {"day": 1, "description": "", "spots": [], "meals": [], "hotel": "", "transport": ""}
    day.update(kwargs)
    return day


def test_breakdown_comes_from_itinerary_actual_prices():
    itinerary = {"days": [
        _day(
            day=1,
            spots=[{"ticket": 60}, {"ticket": 0}],
            meals=[{"cost": 80}, {"cost": 120}],
            hotel="全季酒店（前门店）",
            hotel_price=480,
            transport="地铁",
            transport_cost=20,
        ),
        _day(
            day=2,
            spots=[{"ticket": 40}],
            meals=[{"cost": 100}],
            hotel="全季酒店（前门店）",
            hotel_price=480,
            transport="地铁+步行",
            transport_cost=30,
        ),
        _day(day=3, meals=[{"cost": 90}], transport="机场快轨", transport_cost=15),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=None,
        fallback=_estimate(),
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    # 门票 60+0+40=100/人，餐饮 80+120+100+90=390/人，交通 20+30+15=65/人，住宿 480×1间×2晚
    assert budget["breakdown"]["ticket"] == pytest.approx(200)
    assert budget["breakdown"]["food"] == pytest.approx(780)
    assert budget["breakdown"]["transport"] == pytest.approx(130)
    assert budget["breakdown"]["hotel"] == pytest.approx(960)
    assert budget["total_cost"] == pytest.approx(2070)
    assert budget["rooms"] == 1
    assert budget["nights"] == 2
    assert "行程所选酒店" in budget["basis"]
    assert "实际票价合计" in budget["basis"]


def test_actual_prices_win_over_tier_estimate():
    """同样是 2 人 3 天：行程里的真实花费与档位估算必须不同，且以行程为准"""
    estimate = _estimate()
    itinerary = {"days": [
        _day(day=1, spots=[{"ticket": 300}], meals=[{"cost": 500}], hotel_price=1200, transport_cost=200),
        _day(day=2, spots=[{"ticket": 300}], meals=[{"cost": 500}], hotel_price=1200, transport_cost=200),
        _day(day=3, spots=[{"ticket": 300}], meals=[{"cost": 500}], transport_cost=200),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=None,
        fallback=estimate,
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    assert budget["total_cost"] != pytest.approx(estimate["total_cost"])
    assert budget["breakdown"]["hotel"] == pytest.approx(2400)  # 1200 × 1 间 × 2 晚
    assert budget["breakdown"]["food"] == pytest.approx(3000)   # 1500/人 × 2 人
    assert budget["breakdown"]["ticket"] == pytest.approx(1800)  # 900/人 × 2 人
    assert budget["breakdown"]["transport"] == pytest.approx(1200)  # 600/人 × 2 人


def test_falls_back_per_category_when_itinerary_has_no_price():
    estimate = _estimate()
    itinerary = {"days": [
        _day(day=1, spots=[{"ticket": None}], meals=[{"cost": None}], hotel="某酒店", transport="地铁 1 号线"),
        _day(day=2, spots=[{"ticket": None}], meals=[{"cost": None}], hotel="某酒店", transport="地铁 1 号线"),
        _day(day=3, spots=[], meals=[], hotel="", transport=""),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=None,
        fallback=estimate,
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    assert budget["breakdown"] == estimate["breakdown"]
    assert budget["total_cost"] == pytest.approx(estimate["total_cost"])
    assert "行程内未查到" in budget["basis"]
    # 「地铁 1 号线」没写「元」，不能被当成价格，应退回档位估算
    assert "按「公共交通」30 元/人/天计" in budget["basis"]


def test_transport_fare_text_is_not_used_as_daily_cost():
    """实测：day.transport 里写的是「单程 4—6 元」这类票价，不是当天总花费，不能拿来算预算"""
    itinerary = {"days": [
        _day(day=1, transport="公共交通：地铁+步行，地铁6公里（含）内3元、6—12公里4元，单程普遍4—6元"),
        _day(day=2, transport="公共交通：地铁+公交，地铁起步3元、单程普遍4—6元；公交10公里（含）内2元"),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=None,
        fallback=_estimate(days=2),
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    assert budget["breakdown"]["transport"] == pytest.approx(120)  # 退回档位：30 元/人/天 × 2 人 × 2 天
    assert "行程内未查到实际花费" in budget["basis"]


def test_hotel_price_parsed_from_text_when_numeric_field_missing():
    itinerary = {"days": [
        _day(day=1, hotel="如家酒店（王府井店），约 480 元/晚"),
        _day(day=2, hotel="如家酒店（王府井店），约 480 元/晚"),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=None,
        fallback=_estimate(days=2),
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    assert budget["breakdown"]["hotel"] == pytest.approx(480)


def test_hotel_price_range_takes_middle():
    itinerary = {"days": [
        _day(day=1, hotel="某度假酒店，600–1200 元/晚"),
        _day(day=2, hotel="某度假酒店，600–1200 元/晚"),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=None,
        fallback=_estimate(days=2),
        hotel_preference="中档型酒店",
        traffic_type="公共交通",
    )

    assert budget["breakdown"]["hotel"] == pytest.approx(900)


def test_no_hotel_choice_still_counts_zero():
    itinerary = {"days": [
        _day(day=1, hotel_price=500),
        _day(day=2, hotel_price=500),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=None,
        fallback=_estimate(hotel_preference="不安排住宿"),
        hotel_preference="不安排住宿",
        traffic_type="公共交通",
    )

    assert budget["breakdown"]["hotel"] == 0
    assert "未安排住宿" in budget["basis"]


def test_over_budget_uses_actual_total():
    itinerary = {"days": [
        _day(day=1, spots=[{"ticket": 200}], meals=[{"cost": 300}], hotel_price=800, transport_cost=100),
        _day(day=2, spots=[{"ticket": 200}], meals=[{"cost": 300}], hotel_price=800, transport_cost=100),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=2,
        total_budget=1000,
        fallback=_estimate(days=2),
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    assert budget["total_cost"] > 1000
    assert budget["is_over_budget"] is True
    assert budget["suggestion"].startswith("超出预算")


def test_unpriced_items_are_reported_in_basis():
    itinerary = {"days": [
        _day(day=1, spots=[{"ticket": 60}, {"ticket": None}], meals=[{"cost": 80}, {"cost": None}]),
        _day(day=2, spots=[], meals=[]),
    ]}

    budget = calculate_budget_from_itinerary(
        itinerary=itinerary,
        people_num=1,
        total_budget=None,
        fallback=_estimate(people_num=1, days=2),
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    assert budget["breakdown"]["ticket"] == pytest.approx(60)
    assert budget["breakdown"]["food"] == pytest.approx(80)
    assert "另有 1 个景点未查到票价" in budget["basis"]
    assert "另有 1 餐未查到人均" in budget["basis"]


def test_empty_itinerary_uses_estimate():
    estimate = _estimate()
    budget = calculate_budget_from_itinerary(
        itinerary={"days": []},
        people_num=2,
        total_budget=None,
        fallback=estimate,
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
    )

    assert budget["breakdown"] == estimate["breakdown"]
    assert budget["total_cost"] == pytest.approx(estimate["total_cost"])
