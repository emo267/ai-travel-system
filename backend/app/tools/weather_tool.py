import httpx
from langchain_core.tools import tool

from app.core.config import settings

# 和风的逐日预报按套餐开放，从宽到窄依次尝试
FORECAST_SPANS = ("30d", "15d", "7d", "3d")
TIMEOUT_SECONDS = 20
MAX_SUMMARY_DAYS = 10


def _request(path: str, params: dict) -> dict:
    host = (settings.QWEATHER_API_HOST or "").strip().rstrip("/")
    if host and not host.startswith("http"):
        host = f"https://{host}"

    response = httpx.get(
        f"{host}{path}",
        # lang=zh 才能拿到中文地名与中文天气现象（否则东京会返回「東京/驟雨」）
        params={**params, "key": settings.QWEATHER_API_KEY, "lang": "zh"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()
    if str(payload.get("code")) != "200":
        raise RuntimeError(f"和风天气返回 code={payload.get('code')}")
    return payload


def _lookup_location(destination: str) -> dict | None:
    payload = _request("/geo/v2/city/lookup", {"location": destination, "number": 1})
    locations = payload.get("location") or []
    return locations[0] if locations else None


def _fetch_daily(location_id: str) -> list[dict]:
    last_error = None
    for span in FORECAST_SPANS:
        try:
            payload = _request(f"/v7/weather/{span}", {"location": location_id})
        except Exception as exc:
            last_error = exc
            continue
        daily = payload.get("daily") or []
        if daily:
            return daily
    raise last_error or RuntimeError("和风天气未返回逐日预报")


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _describe(day: dict) -> str:
    text = f"{day.get('fxDate')} {day.get('textDay')} {day.get('tempMin')}~{day.get('tempMax')}℃"
    precip = str(day.get("precip") or "0")
    if precip not in ("0", "0.0"):
        text += f"，降水 {precip}mm"
    return text


def _advice(days: list[dict]) -> str:
    rainy = [d for d in days if str(d.get("precip") or "0") not in ("0", "0.0")]
    lows = [v for v in (_to_int(d.get("tempMin")) for d in days) if v is not None]
    highs = [v for v in (_to_int(d.get("tempMax")) for d in days) if v is not None]

    hints = []
    if rainy:
        hints.append(f"有 {len(rainy)} 天可能降水，建议带伞并准备室内备选行程")
    if lows and min(lows) <= 5:
        hints.append("气温偏低，注意保暖")
    if highs and max(highs) >= 30:
        hints.append("白天偏热，注意防晒补水")
    return "；".join(hints) or "天气整体适宜出行"


def _degraded(destination: str, summary: str) -> dict:
    return {"destination": destination, "forecast": [], "summary": summary, "advice": ""}


@tool
def query_weather(destination: str, start_date: str, end_date: str) -> dict:
    """查询目的地出行期间的天气预报（和风天气）"""
    if not settings.QWEATHER_API_KEY or not settings.QWEATHER_API_HOST:
        return _degraded(destination, "未配置和风天气，暂无天气预报，请按季节常规气候提示。")

    try:
        location = _lookup_location(destination)
        if not location:
            return _degraded(
                destination,
                f"未匹配到「{destination}」的天气站点，暂无天气预报，请按季节常规气候提示。",
            )
        daily = _fetch_daily(location["id"])
    except Exception as exc:
        # 天气只是辅助信息，失败时降级，不能让整个行程生成失败
        print(f"[Weather] 和风天气调用失败，降级处理：{type(exc).__name__}: {exc}")
        return _degraded(destination, "天气服务暂不可用，请按季节常规气候提示。")

    place = location.get("name") or destination
    window = [d for d in daily if start_date <= str(d.get("fxDate")) <= end_date]

    if window:
        shown = window[:MAX_SUMMARY_DAYS]
        detail = "；".join(_describe(d) for d in shown)
        if len(window) > len(shown):
            detail += f"（共 {len(window)} 天，此处列出前 {len(shown)} 天）"
        advice = _advice(window)
        summary = f"{place} {start_date} 至 {end_date} 天气：{detail}。{advice}"
    else:
        # 出行日期超出预报窗口时，不把近期天气塞给模型，避免它当成出行期间的天气
        summary = (
            f"{place} {start_date} 至 {end_date} 的天气预报暂不可得"
            f"（和风天气逐日预报仅覆盖 {daily[0].get('fxDate')} 至 {daily[-1].get('fxDate')}）。"
            f"请按该季节的常规气候提示穿衣与安排行程，不要编造具体天气预报。"
        )
        shown = []
        advice = ""

    forecast = [
        {
            "date": d.get("fxDate"),
            "weather": d.get("textDay"),
            "temp_min": _to_int(d.get("tempMin")),
            "temp_max": _to_int(d.get("tempMax")),
            "precip": d.get("precip"),
        }
        for d in shown
    ]

    return {"destination": place, "forecast": forecast, "summary": summary, "advice": advice}
