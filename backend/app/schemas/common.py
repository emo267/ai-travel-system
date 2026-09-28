from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _to_utc_iso(value: datetime) -> str:
    """naive 时间按 UTC 补上偏移再序列化"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


# 库里所有时间列都是 server_default=func.now()/onupdate=func.now()，由 MySQL 按容器时区
# （UTC）写入。但 naive datetime 序列化出去不带偏移，前端 new Date('...T15:03:42') 会当成
# 本地时间解析，界面上的时间就整整差一个时区（东八区差 8 小时）。
# 补上偏移后浏览器自己换算成本地时间，前端不用改，历史数据也一并正确。
UtcDateTime = Annotated[datetime, PlainSerializer(_to_utc_iso, return_type=str)]
