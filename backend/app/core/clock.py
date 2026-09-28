"""业务时区的当前时间。

服务器（容器）跑在 UTC，而用户在东八区：库里存 UTC 没问题，但「今天是几号」
「这个日期是不是已经过期」必须按用户所在时区判断，否则每天 00:00–08:00 之间
会把北京的前一天当成今天，放过已经开始（或刚过期）的日期。
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def timezone() -> ZoneInfo:
    return ZoneInfo(settings.APP_TIMEZONE)


def now() -> datetime:
    """业务时区的当前时间"""
    return datetime.now(timezone())


def today() -> date:
    """业务时区的今天"""
    return now().date()


def weekday_name(value: date) -> str:
    return WEEKDAY_NAMES[value.weekday()]
