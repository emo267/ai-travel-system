"""高德地图路径规划：把行程里的景点换成真实坐标、开放时间与两两通勤耗时。

和 map_poi_tool 的分工：那个工具是调研阶段按关键词搜 POI（由模型自己调用），
这个是把已经排好的景点解析成坐标、算出景点之间的通勤时间与区域路况，供路线排序用。

接口实测（2026-09，个人版 Key）：
- `v5/place/text` 能拿到 `location` 与 `business.opentime_week`（含淡旺季与闭馆日）；
- `v3/distance` 的 type=1（驾车，耗时已含实时路况）/ type=3（步行）都能用，
  一次请求可带多个起点、但终点只能一个，所以 n 个点要 n-1 次请求；
- `v3/traffic/status/rectangle` 直接返回 INVALID_PARAMS，`circle` 返回 OK 但没有 roads，
  判定个人 Key 没有交通态势权限——取不到就返回 None，由调用方用驾车耗时折算车速。
"""

import math
import time
from typing import Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.tools.map_poi_tool import _in_requested_city  # 复用境外过滤：高德会把「京都」当成北京

POI_ENDPOINT = "https://restapi.amap.com/v5/place/text"
DISTANCE_ENDPOINT = "https://restapi.amap.com/v3/distance"
TRAFFIC_ENDPOINT = "https://restapi.amap.com/v3/traffic/status/circle"

TIMEOUT_SECONDS = 20
QPS_INFOCODE = "10021"
QPS_RETRY_WAIT = 1.2
CALL_INTERVAL = 0.25  # 个人版 Key QPS 很低，主动让一拍，别把额度撞光
MAX_POI_CANDIDATES = 5

DRIVING = 1
WALKING = 3

# 景点名 -> POI 解析结果按进程缓存：同一个景点常跨天重复出现，不重复请求高德
_SPOT_CACHE: Dict[Tuple[str, str], Optional[dict]] = {}


def _get(url: str, params: dict) -> dict:
    """带 QPS 退避的 GET：个人版 Key 连续调用会返回 10021，等一拍重试一次"""
    time.sleep(CALL_INTERVAL)
    payload = httpx.get(
        url,
        params={**params, "key": settings.AMAP_API_KEY},
        timeout=TIMEOUT_SECONDS,
    ).json()
    if str(payload.get("status")) != "1" and str(payload.get("infocode")) == QPS_INFOCODE:
        time.sleep(QPS_RETRY_WAIT)
        payload = httpx.get(
            url,
            params={**params, "key": settings.AMAP_API_KEY},
            timeout=TIMEOUT_SECONDS,
        ).json()
    return payload


def _number(raw) -> Optional[float]:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _pick_poi(payload: dict, name: str, city: str) -> Optional[dict]:
    """从搜索结果里挑最像的那个：先按城市过滤，再优先名称完全一致的"""
    pois = [poi for poi in (payload.get("pois") or []) if _in_requested_city(poi, city)]
    if not pois:
        return None

    exact = [poi for poi in pois if str(poi.get("name") or "").strip() == name.strip()]
    poi = (exact or pois)[0]

    location = str(poi.get("location") or "")
    try:
        lng, lat = (float(part) for part in location.split(","))
    except ValueError:
        return None

    business = poi.get("business") or {}
    return {
        "name": poi.get("name"),
        "lng": lng,
        "lat": lat,
        "address": poi.get("address"),
        "rating": business.get("rating"),
        # opentime_week 比 opentime_today 完整：带淡旺季与「周一全天关闭」这类闭馆说明
        "opentime": business.get("opentime_week") or business.get("opentime_today") or "",
    }


def resolve_spot(name: str, city: str) -> Optional[dict]:
    """把景点名解析成坐标与开放时间；查不到（境外城市、没配 Key、名称太泛）返回 None"""
    key = (city or "", name or "")
    if key in _SPOT_CACHE:
        return _SPOT_CACHE[key]

    result = None
    if settings.AMAP_API_KEY and name:
        try:
            payload = _get(POI_ENDPOINT, {
                "keywords": name,
                "region": city,
                "page_size": MAX_POI_CANDIDATES,
                "show_fields": "business",
            })
            if str(payload.get("status")) == "1":
                result = _pick_poi(payload, name, city)
            else:
                print(
                    f"[Map Route] 解析「{name}」失败：info={payload.get('info')} "
                    f"infocode={payload.get('infocode')}"
                )
        except Exception as exc:
            print(f"[Map Route] 解析「{name}」异常：{type(exc).__name__}: {exc}")

    if result is None:
        print(f"[Map Route] 未解析到「{name}」的坐标（按无地图数据处理）")
    _SPOT_CACHE[key] = result
    return result


def distance_matrix(points: List[dict], type_code: int = DRIVING) -> Dict[Tuple[int, int], dict]:
    """两两之间的耗时与距离，只返回 i < j 的组合。

    高德 v3/distance 一次只能给一个终点，所以按终点分组：第 j 个点一次带上前 j-1 个起点。
    取不到的组合不进字典，调用方会退回直线距离折算。
    """
    matrix: Dict[Tuple[int, int], dict] = {}
    if not settings.AMAP_API_KEY or len(points) < 2:
        return matrix

    for j in range(1, len(points)):
        origins = "|".join(f"{p['lng']:.6f},{p['lat']:.6f}" for p in points[:j])
        try:
            payload = _get(DISTANCE_ENDPOINT, {
                "origins": origins,
                "destination": f"{points[j]['lng']:.6f},{points[j]['lat']:.6f}",
                "type": type_code,
            })
        except Exception as exc:
            print(f"[Map Route] 通勤耗时请求异常：{type(exc).__name__}: {exc}")
            continue

        if str(payload.get("status")) != "1":
            print(f"[Map Route] 通勤耗时返回错误：info={payload.get('info')}")
            continue

        for item in payload.get("results") or []:
            index = _number(item.get("origin_id"))
            minutes = _number(item.get("duration"))
            km = _number(item.get("distance"))
            if index is None or minutes is None or km is None:
                continue
            i = int(index) - 1
            if not 0 <= i < j:
                continue
            if km <= 0.001:  # 两个景点坐标重合，高德会回 1 米 / 1 秒
                minutes, km = 0.0, 0.0
            else:
                minutes, km = minutes / 60, km / 1000
            matrix[(i, j)] = {"minutes": round(minutes, 1), "km": round(km, 2)}

    return matrix


def _span_meters(points: List[dict]) -> float:
    """这组点的外接框对角线长度（米），用来定路况查询半径"""
    lngs = [p["lng"] for p in points]
    lats = [p["lat"] for p in points]
    mid_lat = (min(lats) + max(lats)) / 2
    width = (max(lngs) - min(lngs)) * 111320 * abs(math.cos(math.radians(mid_lat)))
    height = (max(lats) - min(lats)) * 111320
    return (width ** 2 + height ** 2) ** 0.5


def traffic_status(points: List[dict]) -> Optional[dict]:
    """当天的区域实时路况；高德不给数据（个人 Key 无交通态势权限）时返回 None"""
    if not settings.AMAP_API_KEY or not points:
        return None

    lngs = [p["lng"] for p in points]
    lats = [p["lat"] for p in points]
    center = f"{(min(lngs) + max(lngs)) / 2:.6f},{(min(lats) + max(lats)) / 2:.6f}"
    radius = int(min(max(_span_meters(points) / 2 + 500, 800), 5000))

    try:
        payload = _get(TRAFFIC_ENDPOINT, {
            "location": center,
            "radius": radius,
            "extensions": "all",
        })
    except Exception as exc:
        print(f"[Map Route] 路况查询异常：{type(exc).__name__}: {exc}")
        return None

    if str(payload.get("status")) != "1":
        print(f"[Map Route] 路况查询返回错误：info={payload.get('info')}")
        return None

    roads = payload.get("roads") or []
    evaluation = payload.get("evaluation") or {}
    if not roads and not evaluation:
        print("[Map Route] 路况接口无数据（个人 Key 无交通态势权限），改用驾车耗时折算车速")
        return None

    return {
        "description": evaluation.get("description") or "",
        "status": evaluation.get("status") or "",
        "roads": [
            {"name": road.get("name"), "status": road.get("status"), "speed": road.get("speed")}
            for road in roads[:5]
        ],
    }
