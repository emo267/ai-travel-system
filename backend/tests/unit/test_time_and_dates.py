from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.v1.travel import reject_past_start_date
from app.core import clock
from app.schemas.chat_schema import ChatRecordOut

BUSINESS_TZ = timezone(timedelta(hours=8))


class TestUtcDatetimeSerialization:
    """库里的时间都是 MySQL 按 UTC 写的，序列化必须带上偏移，否则前端会差一个时区"""

    def build(self, value):
        return ChatRecordOut(
            record_id=1,
            user_id=1,
            conversation_id=1,
            task_id=None,
            role="user",
            content="hi",
            create_time=value,
        )

    def test_naive_datetime_serializes_as_utc(self):
        dumped = self.build(datetime(2026, 9, 21, 15, 3, 42)).model_dump()
        assert dumped["create_time"] == "2026-09-21T15:03:42+00:00"

    def test_offset_survives_json_roundtrip(self):
        # 这一步是关键：前端拿到的字符串必须能被浏览器识别成 UTC 并换算成 23:03
        dumped = self.build(datetime(2026, 9, 21, 15, 3, 42)).model_dump_json()
        assert "+00:00" in dumped
        assert datetime.fromisoformat("2026-09-21T15:03:42+00:00").astimezone(BUSINESS_TZ).hour == 23

    def test_already_aware_datetime_is_kept(self):
        value = datetime(2026, 9, 21, 15, 3, 42, tzinfo=timezone.utc)
        assert self.build(value).model_dump()["create_time"] == "2026-09-21T15:03:42+00:00"


class TestBusinessClock:
    def test_now_is_in_business_timezone(self):
        now = clock.now()
        assert now.tzinfo is not None
        # 容器跑 UTC，这个值必须是换算过的东八区时间，而不是 UTC
        assert now.utcoffset() == timedelta(hours=8)

        # 比墙钟读数而不是比时刻：两个 aware datetime 相减得到的是同一时刻的差（≈0），
        # 8 小时的差距只体现在读出来的数字上
        wall_now = now.replace(tzinfo=None)
        wall_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((wall_now - wall_utc) - timedelta(hours=8)) < timedelta(seconds=5)

    def test_today_matches_business_timezone(self):
        assert clock.today() == clock.now().date()

    def test_weekday_name_is_chinese(self):
        # 2026-09-21 是周一
        assert clock.weekday_name(date(2026, 9, 21)) == "周一"


class TestChatPromptTimeContext:
    """助手以前只绑了联网搜索、提示词里也没有当前时间，被问「现在几点」只能说不知道"""

    def test_prompt_carries_current_business_time(self):
        from app.api.v1.chat import build_chat_prompt

        prompt = build_chat_prompt(message="现在几点？", history_text="")
        assert "【当前时间】" in prompt
        assert clock.now().strftime("%Y-%m-%d") in prompt
        # 只给时间不够，还要明确禁止它答「我没法知道时间」
        assert "不要说「我没法知道现在几点」" in prompt

    def test_time_tool_is_available_to_chat(self):
        from app.api.v1.chat import CHAT_TOOL_MAP
        from app.tools.time_tool import get_current_datetime

        assert CHAT_TOOL_MAP.get(get_current_datetime.name) is get_current_datetime
        assert get_current_datetime.invoke({})["date"] == clock.today().isoformat()


class TestRejectPastStartDate:
    def test_yesterday_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            reject_past_start_date(clock.today() - timedelta(days=1))
        assert exc.value.status_code == 400
        assert "不能早于今天" in exc.value.detail

    def test_today_is_allowed(self):
        reject_past_start_date(clock.today())

    def test_future_is_allowed(self):
        reject_past_start_date(clock.today() + timedelta(days=30))

    def test_none_is_ignored(self):
        # 更新接口不传开始日期时不应报错
        reject_past_start_date(None)
