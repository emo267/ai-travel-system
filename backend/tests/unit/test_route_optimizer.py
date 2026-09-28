"""路线 Agent 的单测：开放时间解析、排序器、模型顺序的校验与降级"""

import pytest

from app.agents import route_agent as ra


def _point(name, lng=116.4, lat=39.9, open_min=None, close_min=None, dwell=120, closed=""):
    return {
        "name": name,
        "lng": lng,
        "lat": lat,
        "opentime": "",
        "open_min": open_min,
        "close_min": close_min,
        "closed": closed,
        "dwell": dwell,
        "ticket": None,
    }


def _line_matrix(count, minutes_per_hop=10.0):
    """一条直线上的点：i→j 的耗时与序号差成正比，最优路线必须是单向的"""
    matrix = {}
    for i in range(count):
        for j in range(i + 1, count):
            matrix[(i, j)] = {
                "minutes": abs(i - j) * minutes_per_hop,
                "km": float(abs(i - j)),
            }
    return matrix


class TestParseOpenHours:
    def test_reads_first_session_and_closed_day_from_amap_text(self):
        text = (
            "旺季4月1日至10月31日 周二至周日 08:30-17:00 16:00停止检票，"
            "淡季11月1日至3月31日 周二至周日 08:30-16:30 15:30停止检票，"
            "周一全天关闭，节假日营业时间以官方通知为准"
        )

        open_min, close_min, closed = ra.parse_open_hours(text)

        assert open_min == 8 * 60 + 30
        assert close_min == 17 * 60
        assert closed == "一"

    def test_accepts_en_dash_and_fullwidth_colon(self):
        open_min, close_min, _ = ra.parse_open_hours("09：00–18：00")

        assert (open_min, close_min) == (540, 1080)

    def test_unparsable_text_means_no_constraint(self):
        assert ra.parse_open_hours("全天开放") == (None, None, "")
        assert ra.parse_open_hours(None) == (None, None, "")

    def test_cross_midnight_session_is_not_treated_as_closing_time(self):
        open_min, close_min, _ = ra.parse_open_hours("20:00-02:00")

        assert open_min == 1200
        assert close_min is None

    def test_closed_days_are_deduplicated_in_order(self):
        _, _, closed = ra.parse_open_hours("周一闭馆；周二至周日 09:00-17:00；周一全天关闭")

        assert closed == "一"


class TestOptimizeOrder:
    def test_avoids_backtracking_on_a_straight_line(self):
        points = [_point(f"景点{i}", lng=116.4 + i * 0.01) for i in range(4)]

        order = ra.optimize_order(points, _line_matrix(4), day_start=540)

        assert order == [0, 1, 2, 3]
        plan = ra._schedule(order, points, _line_matrix(4), 540, ra.DRIVE_SPEED_KMH)
        assert plan["distance_km"] == 3.0
        assert plan["travel_minutes"] == 30.0

    def test_opening_time_pulls_a_late_opening_spot_to_the_back(self):
        late = _point("下午才开", open_min=14 * 60)
        early = _point("早上就开", open_min=9 * 60)
        matrix = {(0, 1): {"minutes": 0.0, "km": 0.0}}

        order = ra.optimize_order([late, early], matrix, day_start=540)

        assert order == [1, 0]

    def test_early_closing_spot_is_scheduled_first(self):
        flexible = _point("随时能去", dwell=180)
        closing = _point("十一点闭馆", open_min=540, close_min=11 * 60, dwell=120)
        matrix = {(0, 1): {"minutes": 30.0, "km": 5.0}}

        order = ra.optimize_order([flexible, closing], matrix, day_start=540)

        assert order == [1, 0]
        plan = ra._schedule(order, [flexible, closing], matrix, 540, ra.DRIVE_SPEED_KMH)
        assert plan["penalty"] == 0

    def test_waiting_for_opening_is_counted(self):
        first = _point("九点开门", open_min=540)
        second = _point("十一点开门", open_min=660)
        matrix = {(0, 1): {"minutes": 0.0, "km": 0.0}}

        plan = ra._schedule([0, 1], [first, second], matrix, 540, ra.DRIVE_SPEED_KMH)

        assert plan["wait_minutes"] == 0  # 第一个景点九点开门，不用等
        assert plan["stops"][1]["arrival_time"] == "11:00"  # 第二个等到十一点

    def test_single_spot_is_left_alone(self):
        points = [_point("独苗")]

        assert ra.optimize_order(points, {}, day_start=540) == [0]


class TestApplyLlmOrder:
    def _points(self):
        return [_point("故宫"), _point("景山"), _point("北海")]

    def test_maps_names_back_to_indices(self):
        result = ra.RouteDayOutput(
            order=[
                ra.RouteStop(name="北海", duration_minutes=90, reason="顺路"),
                ra.RouteStop(name="故宫", duration_minutes=240, reason="早去"),
                ra.RouteStop(name="景山", duration_minutes=60, reason="顺路"),
            ],
            advice="注意闭馆",
        )

        plan = ra._apply_llm_order(result, self._points())

        assert plan["order"] == [2, 0, 1]
        assert plan["dwells"][0] == 240
        assert plan["reasons"][2] == "顺路"
        assert plan["advice"] == "注意闭馆"

    def test_missing_spot_is_rejected(self):
        result = ra.RouteDayOutput(
            order=[
                ra.RouteStop(name="故宫", duration_minutes=240, reason=""),
                ra.RouteStop(name="景山", duration_minutes=60, reason=""),
            ],
            advice="",
        )

        assert ra._apply_llm_order(result, self._points()) is None

    def test_unknown_name_is_rejected(self):
        result = ra.RouteDayOutput(
            order=[
                ra.RouteStop(name="故宫", duration_minutes=240, reason=""),
                ra.RouteStop(name="景山", duration_minutes=60, reason=""),
                ra.RouteStop(name="天坛", duration_minutes=90, reason=""),
            ],
            advice="",
        )

        assert ra._apply_llm_order(result, self._points()) is None

    def test_duplicated_name_is_rejected(self):
        result = ra.RouteDayOutput(
            order=[
                ra.RouteStop(name="故宫", duration_minutes=240, reason=""),
                ra.RouteStop(name="故宫", duration_minutes=60, reason=""),
                ra.RouteStop(name="景山", duration_minutes=90, reason=""),
            ],
            advice="",
        )

        assert ra._apply_llm_order(result, self._points()) is None

    def test_dwell_is_clamped(self):
        result = ra.RouteDayOutput(
            order=[
                ra.RouteStop(name="故宫", duration_minutes=9999, reason=""),
                ra.RouteStop(name="景山", duration_minutes=1, reason=""),
                ra.RouteStop(name="北海", duration_minutes=90, reason=""),
            ],
            advice="",
        )

        plan = ra._apply_llm_order(result, self._points())

        assert plan["dwells"][0] == ra.MAX_DWELL_MIN
        assert plan["dwells"][1] == ra.MIN_DWELL_MIN


class TestOptimizeDay:
    def _patch_map(self, monkeypatch, opentimes, matrix):
        def fake_resolve(name, city):
            return {
                "name": name,
                "lng": 116.4,
                "lat": 39.9,
                "address": "北京",
                "rating": "4.9",
                "opentime": opentimes.get(name, ""),
            }

        monkeypatch.setattr(ra, "resolve_spot", fake_resolve)
        monkeypatch.setattr(ra, "distance_matrix", lambda points, type_code=1: matrix)
        monkeypatch.setattr(ra, "traffic_status", lambda points: None)

    def _state(self):
        return {
            "destination": "北京",
            "traffic_type": "公共交通",
            "travel_style": "休闲",
            "start_date": "2026-10-03",
        }

    def _day(self):
        return {
            "day": 1,
            "spots": [
                {"name": "随时能去", "ticket": 0, "start_time": "09:00", "duration_minutes": 180},
                {"name": "十一点闭馆", "ticket": 60, "start_time": "09:30", "duration_minutes": 120},
            ],
        }

    def test_uses_the_model_order_when_it_is_feasible(self, monkeypatch):
        self._patch_map(monkeypatch, {}, {(0, 1): {"minutes": 20.0, "km": 3.0}})
        monkeypatch.setattr(
            ra,
            "_ask_expert",
            lambda prompt: ra.RouteDayOutput(
                order=[
                    ra.RouteStop(name="十一点闭馆", duration_minutes=120, reason="十一点就闭馆，先去"),
                    ra.RouteStop(name="随时能去", duration_minutes=180, reason="时间灵活，放后面"),
                ],
                advice="上午路上可能堵",
            ),
        )
        day = self._day()

        plan = ra.optimize_day(day, 0, self._state(), "")

        assert plan["reordered"] is True
        assert [spot["name"] for spot in day["spots"]] == ["十一点闭馆", "随时能去"]
        assert day["route"]["optimized"] is True
        assert day["route"]["advice"] == "上午路上可能堵"
        assert day["route"]["stops"][0]["reason"] == "十一点就闭馆，先去"
        assert day["route"]["source"] == "高德路径规划 + 路线优化模型"

    def test_falls_back_when_the_model_order_misses_closing_time(self, monkeypatch, capsys):
        self._patch_map(monkeypatch, {"十一点闭馆": "09:00-11:00"}, {(0, 1): {"minutes": 30.0, "km": 5.0}})
        monkeypatch.setattr(
            ra,
            "_ask_expert",
            lambda prompt: ra.RouteDayOutput(
                order=[
                    ra.RouteStop(name="随时能去", duration_minutes=180, reason="先去"),
                    ra.RouteStop(name="十一点闭馆", duration_minutes=120, reason="后去"),
                ],
                advice="",
            ),
        )
        day = self._day()

        plan = ra.optimize_day(day, 0, self._state(), "")

        # 模型把十一点闭馆的景点排到了最后，代码算出的顺序不会，所以以代码为准
        assert [spot["name"] for spot in day["spots"]] == ["十一点闭馆", "随时能去"]
        assert plan["reordered"] is True  # 相对主规划师的顺序确实变了
        assert day["route"]["stops"][0]["reason"] == ""  # 用的是代码顺序，模型给的理由不带过来
        assert "改用代码算的顺序" in capsys.readouterr().out
        assert day["route"]["source"] == "高德路径规划 + 路线优化模型"

    def test_falls_back_when_the_model_call_fails(self, monkeypatch):
        self._patch_map(monkeypatch, {}, {(0, 1): {"minutes": 30.0, "km": 5.0}})
        monkeypatch.setattr(ra, "_ask_expert", lambda prompt: None)
        day = self._day()

        plan = ra.optimize_day(day, 0, self._state(), "")

        assert day["route"]["source"] == "高德路径规划"
        assert plan["reordered"] is False

    def test_itinerary_opentime_is_used_when_amap_has_none(self, monkeypatch):
        self._patch_map(monkeypatch, {}, {(0, 1): {"minutes": 30.0, "km": 5.0}})
        monkeypatch.setattr(ra, "_ask_expert", lambda prompt: None)
        day = self._day()
        day["spots"][1]["opentime"] = "09:00-11:00"

        ra.optimize_day(day, 0, self._state(), "")

        assert [spot["name"] for spot in day["spots"]] == ["十一点闭馆", "随时能去"]

    def test_unresolvable_spot_keeps_the_original_order(self, monkeypatch):
        def fake_resolve(name, city):
            if name == "十一点闭馆":
                return None
            return {"name": name, "lng": 116.4, "lat": 39.9, "address": "", "rating": "", "opentime": ""}

        monkeypatch.setattr(ra, "resolve_spot", fake_resolve)
        monkeypatch.setattr(ra, "distance_matrix", lambda points, type_code=1: {})
        monkeypatch.setattr(ra, "traffic_status", lambda points: None)
        day = self._day()

        assert ra.optimize_day(day, 0, self._state(), "") is None
        assert [spot["name"] for spot in day["spots"]] == ["随时能去", "十一点闭馆"]
        assert day["route"]["optimized"] is False
        assert "十一点闭馆" in day["route"]["note"]

    def test_single_spot_day_is_skipped(self, monkeypatch):
        day = {"day": 1, "spots": [{"name": "只有一个", "start_time": "09:00"}]}

        assert ra.optimize_day(day, 0, self._state(), "") is None
        assert "route" not in day

    def test_transport_override_is_applied_even_when_skipped(self):
        day = {"day": 1, "spots": [{"name": "只有一个", "start_time": "09:00"}]}

        ra.optimize_day(day, 0, self._state(), "自驾")

        assert day["transport"] == "自驾"


class TestRouteAgentNode:
    def test_empty_itinerary_is_reported(self):
        result = ra.route_agent_node({"itinerary": {"days": []}})

        assert result["route_plan"]["optimized"] is False
        assert result["route_plan"]["days"] == []

    def test_node_rewrites_spots_and_keeps_transport(self, monkeypatch):
        monkeypatch.setattr(
            ra,
            "resolve_spot",
            lambda name, city: {
                "name": name,
                "lng": 116.4,
                "lat": 39.9,
                "address": "",
                "rating": "",
                "opentime": "09:00-17:00",
            },
        )
        monkeypatch.setattr(
            ra, "distance_matrix", lambda points, type_code=1: {(0, 1): {"minutes": 20.0, "km": 3.0}}
        )
        monkeypatch.setattr(ra, "traffic_status", lambda points: None)
        monkeypatch.setattr(
            ra,
            "_ask_expert",
            lambda prompt: ra.RouteDayOutput(
                order=[
                    ra.RouteStop(name="甲", duration_minutes=120, reason="顺路"),
                    ra.RouteStop(name="乙", duration_minutes=60, reason="顺路"),
                ],
                advice="",
            ),
        )
        state = {
            "destination": "北京",
            "traffic_type": "自驾",
            "travel_style": "休闲",
            "start_date": "2026-10-03",
            "itinerary": {
                "days": [
                    {
                        "day": 1,
                        "spots": [
                            {"name": "甲", "ticket": 0, "start_time": "09:00", "duration_minutes": 120},
                            {"name": "乙", "ticket": 0, "start_time": "13:00", "duration_minutes": 60},
                        ],
                    }
                ]
            },
        }

        result = ra.route_agent_node(state)

        day = state["itinerary"]["days"][0]
        assert day["transport"] == "自驾"  # 旧行为保留
        assert day["route_optimized"] is True
        assert result["route_plan"]["optimized"] is True
        assert result["route_plan"]["days"][0]["total_distance_km"] == 3.0

    def test_transport_is_not_overridden_for_mixed_choices(self, monkeypatch):
        monkeypatch.setattr(ra, "resolve_spot", lambda name, city: None)
        day = {
            "day": 1,
            "transport": "地铁+步行",
            "spots": [
                {"name": "甲", "start_time": "09:00"},
                {"name": "乙", "start_time": "13:00"},
            ],
        }
        state = {"destination": "北京", "traffic_type": "自驾、公共交通", "itinerary": {"days": [day]}}

        ra.route_agent_node(state)

        assert day["transport"] == "地铁+步行"


@pytest.mark.parametrize(
    "value,expected",
    [(None, ra.DEFAULT_DWELL_MIN), ("abc", ra.DEFAULT_DWELL_MIN), (5, ra.MIN_DWELL_MIN), (999, ra.MAX_DWELL_MIN), (90, 90)],
)
def test_clamp_dwell(value, expected):
    assert ra._clamp_dwell(value) == expected


def test_time_helpers():
    assert ra._to_minutes("09:30") == 570
    assert ra._to_minutes("24:00") is None
    assert ra._to_hhmm(570) == "09:30"
    assert ra._humanize(70) == "1 小时 10 分"
    assert ra._humanize(45) == "45 分钟"
    assert ra._humanize(120) == "2 小时"
