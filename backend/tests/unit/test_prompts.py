"""提示词集中管理后的回归测试：渲染出的文本要完整、占位符要全部替换掉"""

from app.agents.prompts import (
    RESEARCH_SUMMARY_PROMPT,
    RESEARCH_SYSTEM_PROMPT,
    REVIEW_SYSTEM_PROMPT,
    ROUTE_EXPERT_PROMPT,
    itinerary_prompt,
    price_hints_prompt,
    research_kickoff_prompt,
    review_user_prompt,
    route_day_prompt,
)


def test_fixed_prompts_are_not_empty_and_keep_key_constraints():
    for text in (
        RESEARCH_SYSTEM_PROMPT,
        RESEARCH_SUMMARY_PROMPT,
        ROUTE_EXPERT_PROMPT,
        REVIEW_SYSTEM_PROMPT,
    ):
        assert text.strip()

    assert "旅行数据调研员" in RESEARCH_SYSTEM_PROMPT
    assert "路线优化专家" in ROUTE_EXPERT_PROMPT
    assert "行程评审员" in REVIEW_SYSTEM_PROMPT


def test_prompts_that_produce_visible_chinese_carry_the_simplified_rule():
    """调研笔记、路线建议、评审理由都会展示给用户，必须显式约束简体"""
    assert "简体中文" in RESEARCH_SYSTEM_PROMPT
    assert "简体中文" in ROUTE_EXPERT_PROMPT
    assert "简体中文" in REVIEW_SYSTEM_PROMPT


def test_research_kickoff_prompt_carries_the_brief():
    text = research_kickoff_prompt("目的地：北京\n人数：2 人")

    assert "目的地：北京" in text
    assert "请开始查证" in text


def test_price_hints_prompt_carries_preference_and_notes():
    text = price_hints_prompt(hotel_preference="经济型酒店", research="如家 480 元/晚")

    assert "经济型酒店" in text
    assert "如家 480 元/晚" in text
    assert "不要凭常识估算" in text


def test_itinerary_prompt_fills_every_block():
    text = itinerary_prompt(
        destination="北京",
        start_date="2026-10-03",
        end_date="2026-10-05",
        people_desc="2 人（1 男 1 女）",
        budget_desc="4000 元",
        hotel_preference="经济型酒店",
        travel_style="休闲",
        traffic_type="公共交通",
        extra_require="不要太赶",
        weather_summary="晴，18-26℃",
        budget_line="总花费预估 3200 元（按行程实际价格核算）",
        research_text="故宫门票 60 元",
        rag_text="故宫周一闭馆",
        review_block="\n    【上次评审意见】（这次必须针对性修正）\n    - 第 1 天太赶\n",
    )

    for fragment in (
        "北京",
        "2026-10-03 至 2026-10-05",
        "2 人（1 男 1 女）",
        "4000 元",
        "经济型酒店",
        "休闲",
        "公共交通",
        "不要太赶",
        "晴，18-26℃",
        "总花费预估 3200 元",
        "故宫门票 60 元",
        "故宫周一闭馆",
        "第 1 天太赶",
        "【填写要求】",
        "【上次评审意见】",
    ):
        assert fragment in text

    assert "{" not in text and "}" not in text  # 占位符必须全部替换
    assert "简体中文" in text  # 行程正文会直接展示给用户


def test_itinerary_prompt_has_no_review_block_by_default():
    text = itinerary_prompt(
        destination="北京",
        start_date="2026-10-03",
        end_date="2026-10-03",
        people_desc="2 人",
        budget_desc="未设置（不限制）",
        hotel_preference="经济型酒店",
        travel_style="休闲",
        traffic_type="公共交通",
        extra_require="",
        weather_summary="",
        budget_line="",
        research_text="",
        rag_text="",
    )

    assert "【上次评审意见】" not in text


def test_route_day_prompt_fills_every_block():
    text = route_day_prompt(
        day_number=2,
        date_text="2026-10-04",
        weekday="周日",
        destination="北京",
        traffic_type="公共交通",
        travel_style="休闲",
        start_time="09:00",
        original_order="故宫博物院 → 颐和园",
        closed_note="需要注意的闭馆安排：故宫周一全天关闭",
        spot_lines="1. 故宫博物院（08:30-17:00）",
        leg_lines="故宫博物院 → 颐和园：驾车 42 分钟 / 21.8 公里",
        traffic_text="畅通（平均车速约 36 公里/小时）",
        dwell_range="30-360",
        point_count=2,
    )

    for fragment in (
        "第 2 天",
        "2026-10-04 周日",
        "北京",
        "公共交通",
        "休闲",
        "09:00",
        "故宫博物院 → 颐和园",
        "故宫周一全天关闭",
        "1. 故宫博物院（08:30-17:00）",
        "驾车 42 分钟 / 21.8 公里",
        "畅通（平均车速约 36 公里/小时）",
        "30-360 分钟",
        "全部 2 个景点",
    ):
        assert fragment in text

    assert "{" not in text and "}" not in text


def test_route_day_prompt_says_unlimited_when_preference_missing():
    text = route_day_prompt(
        day_number=1,
        date_text="2026-10-03",
        weekday="周六",
        destination="北京",
        traffic_type="",
        travel_style="",
        start_time="09:00",
        original_order="天安门广场",
        closed_note="",
        spot_lines="1. 天安门广场",
        leg_lines="",
        traffic_text="未获取到路况数据",
        dwell_range="30-360",
        point_count=1,
    )

    assert "出行方式：不限" in text
    assert "游玩风格：不限" in text


def test_review_user_prompt_fills_every_block():
    text = review_user_prompt(
        destination="北京",
        start_date="2026-10-03",
        end_date="2026-10-05",
        day_count=3,
        people_num=2,
        budget_desc="4000元",
        hotel_preference="经济型酒店",
        travel_style="休闲",
        traffic_type="公共交通",
        extra_require="",
        weather_summary="晴",
        budget_line="总花费预估 3200 元",
        rule_text="- 规则预检未发现问题",
        itinerary_json='{"destination": "北京"}',
    )

    for fragment in (
        "北京",
        "2026-10-03 至 2026-10-05（共 3 天）",
        "2 人",
        "4000元",
        "经济型酒店",
        "休闲",
        "公共交通",
        "额外需求：无",
        "晴",
        "总花费预估 3200 元",
        "- 规则预检未发现问题",
        '{"destination": "北京"}',
        "【评审要求】",
    ):
        assert fragment in text

    assert "{" not in text.replace('{"destination": "北京"}', "")  # 除行程 JSON 外不得残留占位符
