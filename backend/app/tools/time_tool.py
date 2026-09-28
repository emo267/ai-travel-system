from langchain_core.tools import tool

from app.core import clock
from app.core.config import settings


@tool
def get_current_datetime() -> dict:
    """获取当前的真实日期与时间。

    需要知道「今天是几号」「现在几点」「离出行还有几天」时调用它，
    不要凭记忆猜当前日期。返回业务时区的日期、时间与星期。
    """
    current = clock.now()
    return {
        "date": current.strftime("%Y-%m-%d"),
        "time": current.strftime("%H:%M:%S"),
        "weekday": clock.weekday_name(current),
        "datetime": current.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": settings.APP_TIMEZONE,
    }
