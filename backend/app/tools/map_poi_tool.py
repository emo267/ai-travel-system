import time

import httpx
from langchain_core.tools import tool

from app.core.config import settings

AMAP_ENDPOINT = "https://restapi.amap.com/v5/place/text"
TIMEOUT_SECONDS = 20
MAX_RESULTS = 10
QPS_INFOCode = "10021"
QPS_RETRY_WAIT = 1.2


def _parse_location(raw) -> tuple[float | None, float | None]:
    try:
        lng, lat = str(raw).split(",")
        return float(lng), float(lat)
    except (ValueError, AttributeError):
        return None, None


def _in_requested_city(poi: dict, destination: str) -> bool:
    # 高德不覆盖境外：搜「京都 景点」会返回故宫/天安门（把京都当成了首都），
    # 搜「东京」会返回开封的景点（开封古称东京）。必须用行政区名把这类结果挡掉。
    for field in ("cityname", "adname", "pname"):
        if destination and destination in str(poi.get(field) or ""):
            return True
    return False


def _request(params: dict) -> dict:
    response = httpx.get(
        AMAP_ENDPOINT,
        params={
            **params,
            "key": settings.AMAP_API_KEY,
            "page_size": MAX_RESULTS,
            "show_fields": "business",
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _to_dict(poi: dict) -> dict:
    business = poi.get("business") or {}
    lng, lat = _parse_location(poi.get("location"))
    return {
        "name": poi.get("name"),
        "type": (poi.get("type") or "").split(";")[0],
        "address": poi.get("address"),
        "lng": lng,
        "lat": lat,
        "rating": business.get("rating"),
        "tel": business.get("tel"),
        "opentime": business.get("opentime_today"),
    }


@tool
def search_poi(destination: str, keyword: str) -> list:
    """搜索目的地的景点、酒店、餐厅等 POI（高德地图）"""
    if not settings.AMAP_API_KEY:
        print("[Map POI] 未配置高德 Key，跳过 POI 搜索")
        return []

    params = {"keywords": keyword, "region": destination}
    try:
        payload = _request(params)
        # 个人版 QPS 很低，连续调用会撞限额，等一拍重试一次
        if str(payload.get("status")) != "1" and str(payload.get("infocode")) == QPS_INFOCode:
            time.sleep(QPS_RETRY_WAIT)
            payload = _request(params)
    except Exception as exc:
        print(f"[Map POI] 高德调用失败，返回空列表：{type(exc).__name__}: {exc}")
        return []

    if str(payload.get("status")) != "1":
        print(
            f"[Map POI] 高德返回错误：info={payload.get('info')} "
            f"infocode={payload.get('infocode')}"
        )
        return []

    pois = payload.get("pois") or []
    results = [_to_dict(poi) for poi in pois if _in_requested_city(poi, destination)]

    if not results and pois:
        print(
            f"[Map POI]「{destination}」返回的 {len(pois)} 条都不是该城市的 POI，"
            f"判定高德不覆盖该目的地（境外城市无数据）"
        )
    return results
