"""关联行程必须真的被助手读到。

以前 task_id 只是存进聊天记录，行程内容从没进过提示词：用户选了行程再问「第三天住哪儿」，
助手照样去联网搜，所以「关联行程」是个摆设。
"""

from datetime import date
from types import SimpleNamespace

from app.api.v1.chat import build_chat_prompt
from app.services import plan_context
from app.services.plan_context import build_plan_brief, load_linked_plan, plan_label


def _task(**kwargs):
    base = dict(
        task_id=7,
        destination="北京",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 2),
        people_num=2,
        total_budget=4000,
        hotel_preference="经济型酒店",
        traffic_type="公共交通",
        travel_style="休闲",
        extra_require="",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _plan(itinerary, total_cost=2038, weather_summary="晴，10~22℃"):
    return SimpleNamespace(
        plan_id=1,
        task_id=7,
        total_cost=total_cost,
        weather_summary=weather_summary,
        itinerary=itinerary,
    )


FULL_ITINERARY = {
    "days": [
        {
            "day": 1,
            "date": "2026-10-01",
            "spots": [
                {"name": "故宫博物院", "ticket": 60, "start_time": "09:00", "duration_minutes": 180},
                {"name": "天安门广场", "ticket": 0, "start_time": "12:30", "duration_minutes": 60},
            ],
            "meals": [{"name": "护国寺小吃", "cost": 30}],
            "hotel": "如家（雍和宫和平里东街店）",
            "hotel_price": 850,
            "transport": "地铁+公交",
            "transport_cost": 30,
            "description": "上午看故宫，下午去天安门广场。故宫需提前预约，周一闭馆。",
        },
        {
            "day": 2,
            "date": "2026-10-02",
            "spots": [{"name": "八达岭长城", "ticket": 40, "start_time": "08:00"}],
            "meals": [],
            "hotel": "",
            "transport": "市郊铁路S2线",
            "description": "去八达岭长城，建议早出发避开人流。",
        },
    ],
    "summary": "两天节奏适中，第一天市区、第二天近郊。",
    "budget": {
        "breakdown": {"hotel": 850, "food": 820, "transport": 120, "ticket": 248},
        "basis": "住宿按行程所选酒店的 850 元/间/晚 × 1 间 × 1 晚计；餐饮按行程内 4 餐的实际人均合计 410 元/人",
    },
    "review": {"summary": "行程合理，预算充足。"},
}


def test_brief_carries_every_day_and_the_actual_prices():
    brief = build_plan_brief(_task(), _plan(FULL_ITINERARY))

    assert "目的地：北京" in brief
    assert "日期：2026-10-01 至 2026-10-02" in brief
    assert "人数：2 人" in brief
    assert "预算：4,000 元" in brief

    assert "第 1 天（2026-10-01）" in brief
    assert "故宫博物院" in brief and "门票 60 元/人" in brief
    assert "天安门广场" in brief and "免费" in brief
    assert "护国寺小吃（人均 30 元）" in brief
    assert "850 元/间/晚" in brief
    assert "人均 30 元/天" in brief

    assert "第 2 天（2026-10-02）" in brief
    assert "八达岭长城" in brief

    assert "总花费 2,038 元" in brief
    assert "住宿 850 元" in brief and "门票 248 元" in brief
    assert "预算口径" in brief
    assert "晴，10~22℃" in brief


def test_brief_marks_items_without_a_known_price():
    itinerary = {
        "days": [
            {
                "day": 1,
                "spots": [{"name": "某公园"}],
                "meals": [{"name": "路边小馆"}],
                "hotel": "某民宿",
            }
        ]
    }
    brief = build_plan_brief(_task(), _plan(itinerary))

    assert "某公园（门票待确认）" in brief
    assert "路边小馆（人均待确认）" in brief
    assert "某民宿" in brief


def test_brief_tells_the_assistant_when_the_plan_is_not_ready():
    brief = build_plan_brief(_task(), _plan({"days": []}))

    assert "还没有生成出每日安排" in brief
    assert "提醒用户等行程生成完成" in brief


def test_brief_works_when_there_is_no_plan_row_yet():
    brief = build_plan_brief(_task(), None)

    assert "目的地：北京" in brief
    assert "还没有生成出每日安排" in brief


def test_prompt_carries_the_plan_and_the_rules_for_using_it():
    prompt = build_chat_prompt(
        message="第三天住哪儿？",
        history_text="",
        plan_brief="【行程基本信息】目的地：北京；日期：2026-10-01 至 2026-10-02",
    )

    assert "【关联行程】（用户本次选定的行程，回答前必须先读完）" in prompt
    assert "【行程基本信息】目的地：北京" in prompt
    assert "【关联行程的使用要求】" in prompt
    # 行程里已写清楚的直接答，只有实时信息才联网
    assert "直接据此回答，不需要联网" in prompt
    assert "才调用 web_search 核实" in prompt
    # 有关联行程时，依据优先级要把行程排在联网前面
    assert "与【关联行程】有关的问题，先依据行程里的内容回答。" in prompt
    assert "优先依据【联网搜索结果】回答" not in prompt


def test_prompt_without_a_plan_keeps_the_old_priority():
    prompt = build_chat_prompt(message="北京有什么好玩的", history_text="")

    assert "【关联行程】" not in prompt
    assert "优先依据【联网搜索结果】回答" in prompt


def test_plan_label_names_the_trip():
    assert plan_label(_task()) == "北京 · 2026-10-01 至 2026-10-02"


def test_load_linked_plan_returns_nothing_without_a_task_id():
    assert load_linked_plan(None, 1, None) == (None, None)
    assert load_linked_plan(None, 1, 0) == (None, None)


def test_load_linked_plan_checks_ownership_before_reading_the_plan(monkeypatch):
    """task_id 来自客户端，别人的行程不能读出来"""
    read_plans = []
    monkeypatch.setattr(
        plan_context.travel_service, "get_travel_task", lambda db, user_id, task_id: None
    )
    monkeypatch.setattr(
        plan_context.travel_service,
        "get_travel_plan_by_task",
        lambda db, task_id: read_plans.append(task_id),
    )

    assert load_linked_plan(object(), 1, 7) == (None, None)
    assert read_plans == []
