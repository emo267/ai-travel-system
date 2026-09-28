"""评审 Agent 的单测：主观维度加权、规则分上限、模型失败降级、重排信号。

评审模型本身不联网也不调用大模型——这里全部用假 LLM 顶替，
验证的是「代码怎么处理模型给的维度分」，而不是模型答得好不好。
"""

import pytest

from app.agents import review_agent
from app.agents.review_agent import (
    DIMENSION_WEIGHTS,
    ReviewOutput,
    _weighted_score,
    review_agent_node,
)

ALL_HIGH = [
    {"name": "节奏", "score": 100, "comment": "松紧有致"},
    {"name": "餐饮", "score": 100, "comment": "搭配合理"},
    {"name": "交通", "score": 100, "comment": "全程顺路"},
    {"name": "预算", "score": 100, "comment": "结余充裕"},
    {"name": "偏好", "score": 100, "comment": "照顾到位"},
]


def _state(*, days=None, is_over_budget=False, retry_count=0):
    itinerary = {
        "days": days if days is not None else [{"day": 1, "spots": [{"name": "故宫"}]}]
    }
    return {
        "destination": "北京",
        "start_date": "2026-10-03",
        "end_date": "2026-10-04",
        "people_num": 2,
        "total_budget": 4000,
        "hotel_preference": "经济型酒店",
        "travel_style": "休闲",
        "traffic_type": "公共交通",
        "extra_require": "",
        "weather_data": {"summary": "晴"},
        "budget_plan": {
            "total_cost": 3200,
            "basis": "按行程里的实际价格算",
            "suggestion": "预算充足，预计结余 ¥800",
            "is_over_budget": is_over_budget,
        },
        "itinerary": itinerary,
        "retry_count": retry_count,
    }


def _review_output(**overrides):
    payload = {
        "summary": "整体不错，第 2 天偏紧",
        "explanation": "第 1 天节奏舒适。第 2 天景点偏多，建议挪一个到第 3 天。",
        "dimensions": [
            {"name": "节奏", "score": 82, "comment": "第 2 天排了 5 个景点"},
            {"name": "餐饮", "score": 88, "comment": "餐厅都在动线上"},
            {"name": "交通", "score": 76, "comment": "第 2 天有一段折返"},
            {"name": "预算", "score": 90, "comment": "离预算还有余量"},
            {"name": "偏好", "score": 84, "comment": "住宿档次符合要求"},
        ],
        "suggestions": ["第 2 天把颐和园挪到上午，下午回市区"],
        "issues": [],
        "needs_regeneration": False,
    }
    payload.update(overrides)
    return ReviewOutput(**payload)


class _FakeStructured:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages)
        if self._error is not None:
            raise self._error
        return self._result


class _FakeLLM:
    def __init__(self, structured):
        self._structured = structured

    def with_structured_output(self, _schema):
        return self._structured


def _patch_llm(monkeypatch, structured):
    monkeypatch.setattr(review_agent, "get_llm", lambda temperature=0: _FakeLLM(structured))
    return structured


# ---------------------------------------------------------------- 维度加权


def test_weighted_score_uses_declared_weights():
    dimensions = [
        {"name": "节奏", "score": 100},  # 0.25
        {"name": "餐饮", "score": 50},  # 0.20
        {"name": "交通", "score": 70},  # 0.20
        {"name": "预算", "score": 60},  # 0.15
        {"name": "偏好", "score": 80},  # 0.20
    ]

    # 25 + 10 + 14 + 9 + 16 = 74
    assert _weighted_score(dimensions) == 74


def test_weighted_score_normalizes_when_dimensions_are_missing():
    """模型漏给维度时按剩下的权重归一化，不能把缺项当成 0 分"""
    # (0.25×100 + 0.20×0) / 0.45 = 55.6 → 56
    assert _weighted_score([{"name": "节奏", "score": 100}, {"name": "餐饮", "score": 0}]) == 56
    assert _weighted_score([{"name": "交通", "score": 88}]) == 88


def test_weighted_score_ignores_unknown_dimension_names():
    assert _weighted_score([{"name": "趣味", "score": 0}, {"name": " 节奏 ", "score": 90}]) == 90


def test_weighted_score_returns_none_without_any_dimension():
    assert _weighted_score([]) is None
    assert _weighted_score(None) is None


def test_weighted_score_clamps_out_of_range_scores():
    assert _weighted_score([{"name": "节奏", "score": 150}]) == 100
    assert _weighted_score([{"name": "节奏", "score": -20}]) == 0


def test_prompt_mentions_every_weighted_dimension():
    """权重表的键必须出现在提示词里，否则模型给的维度名对不上、分数会被整体丢弃"""
    from app.agents.prompts import review_user_prompt

    prompt = review_user_prompt(
        destination="北京",
        start_date="2026-10-03",
        end_date="2026-10-04",
        day_count=2,
        people_num=2,
        budget_desc="4000元",
        hotel_preference="经济型酒店",
        travel_style="休闲",
        traffic_type="公共交通",
        extra_require="",
        weather_summary="晴",
        budget_line="总花费预估 3200 元",
        rule_text="- 规则预检未发现问题",
        itinerary_json="{}",
    )

    for name in DIMENSION_WEIGHTS:
        assert name in prompt


# ------------------------------------------------------------------ 节点


def test_node_uses_weighted_score_and_keeps_details(monkeypatch):
    structured = _patch_llm(monkeypatch, _FakeStructured(result=_review_output()))

    result = review_agent_node(_state())
    report = result["review_report"]
    weighted = _weighted_score(report["dimensions"])

    assert report["score"] == weighted == result["review_score"]
    assert [item["name"] for item in report["dimensions"]] == ["节奏", "餐饮", "交通", "预算", "偏好"]
    assert report["dimensions"][0]["comment"] == "第 2 天排了 5 个景点"
    assert report["suggestions"] == ["第 2 天把颐和园挪到上午，下午回市区"]
    assert result["retry_count"] == 1
    # 传给模型的是 system + user 两条消息
    assert len(structured.prompts[0]) == 2


def test_rule_score_caps_weighted_score(monkeypatch):
    """维度分打得再高，超预算也不该拿满分"""
    _patch_llm(monkeypatch, _FakeStructured(result=_review_output(dimensions=ALL_HIGH)))

    report = review_agent_node(_state(is_over_budget=True))["review_report"]

    assert report["score"] == 80  # 规则分 100-20，低于维度分 100


def test_low_weighted_score_is_kept(monkeypatch):
    """维度分低于规则分时以维度分为准（规则没问题不等于行程舒服）"""
    low = [{"name": "节奏", "score": 40, "comment": "排得太满"}]
    _patch_llm(monkeypatch, _FakeStructured(result=_review_output(dimensions=low)))

    assert review_agent_node(_state())["review_score"] == 40


def test_node_falls_back_to_rule_score_when_model_fails(monkeypatch):
    _patch_llm(monkeypatch, _FakeStructured(error=RuntimeError("model down")))

    result = review_agent_node(_state())

    assert result["review_score"] == 100
    assert result["review_report"]["dimensions"] == []
    assert result["review_report"]["suggestions"] == []
    assert result["review_feedback"] == []


def test_busy_day_triggers_regeneration_feedback(monkeypatch):
    days = [{"day": 1, "spots": [{"name": f"景点{i}"} for i in range(6)]}]
    issues = ["第 1 天安排了 6 个景点，走不完"]
    _patch_llm(
        monkeypatch,
        _FakeStructured(
            result=_review_output(dimensions=ALL_HIGH, issues=issues, needs_regeneration=True)
        ),
    )

    result = review_agent_node(_state(days=days))

    # 维度分满分，但规则扣了 15 分 → 取 85
    assert result["review_score"] == 85
    assert result["review_feedback"] == issues


def test_feedback_stays_empty_when_regeneration_is_not_needed(monkeypatch):
    """模型说不用重排就留空：重排要重跑联网调研 + 三次大模型调用，代价太高"""
    _patch_llm(
        monkeypatch,
        _FakeStructured(result=_review_output(issues=["第 2 天偏紧"], needs_regeneration=False)),
    )

    assert review_agent_node(_state())["review_feedback"] == []


@pytest.mark.parametrize("value", [0, 100])
def test_score_is_clamped_to_valid_range(monkeypatch, value):
    dims = [{"name": "节奏", "score": v, "comment": "x"} for v in [value] * 5]
    _patch_llm(monkeypatch, _FakeStructured(result=_review_output(dimensions=dims)))

    assert review_agent_node(_state())["review_score"] == value
