from datetime import datetime, timedelta

from app.db.models.chat_record import ChatRecord
from app.services.chat_service import _split_by_gap, _title_source, make_title

BASE = datetime(2026, 9, 19, 10, 18, 0)


def record(role: str, content: str, offset: timedelta = timedelta()) -> ChatRecord:
    return ChatRecord(role=role, content=content, create_time=BASE + offset)


class TestMakeTitle:
    def test_truncates_to_limit(self):
        assert make_title("一" * 50) == "一" * 20

    def test_collapses_whitespace_and_newlines(self):
        assert make_title("  珠海\n有什么   好玩的  ") == "珠海 有什么 好玩的"

    def test_empty_becomes_placeholder(self):
        assert make_title("") == "新对话"
        assert make_title("   \n  ") == "新对话"


class TestSplitByGap:
    def test_uses_first_user_message_as_title(self):
        group = [record("assistant", "开场白"), record("user", "珠海有什么好玩的")]
        assert _title_source(group) == "珠海有什么好玩的"

    def test_falls_back_to_first_record_when_no_user_message(self):
        group = [record("assistant", "只有助手说话"), record("assistant", "还是助手")]
        assert _title_source(group) == "只有助手说话"

    def test_gap_exactly_two_hours_stays_in_one_group(self):
        # 边界是「超过」2 小时才另起一段，正好 2 小时仍算同一轮
        records = [record("user", "a"), record("user", "b", timedelta(hours=2))]
        assert [_title_source(group) for group in _split_by_gap(records, timedelta(hours=2))] == ["a"]

    def test_gap_over_two_hours_starts_new_group(self):
        records = [
            record("user", "a"),
            record("user", "b", timedelta(hours=2, seconds=1)),
        ]
        groups = _split_by_gap(records, timedelta(hours=2))
        assert len(groups) == 2
        assert [_title_source(group) for group in groups] == ["a", "b"]

    def test_matches_the_shape_of_real_history(self):
        # 复刻库里用户 9 的真实分布：09-19 那一轮（08:00~10:00 连续）
        # 与 09-21 那一轮（06:58 起），中间隔了一天多，应拆成两段
        records = [
            record("user", "你好"),
            record("assistant", "你好呀", timedelta(minutes=3)),
            record("user", "珠海有什么好玩的", timedelta(days=1, hours=20)),
            record("assistant", "珠海超好玩的", timedelta(days=1, hours=20, minutes=1)),
        ]
        groups = _split_by_gap(records, timedelta(hours=2))
        assert len(groups) == 2
        assert [_title_source(group) for group in groups] == ["你好", "珠海有什么好玩的"]
        assert [len(group) for group in groups] == [2, 2]
