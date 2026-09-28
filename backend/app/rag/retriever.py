from functools import lru_cache

from app.rag.vector_store import get_vector_store

# Chroma 默认 L2 距离，越小越相似。
# 实测：相关查询 0.65~0.90，无关查询 0.89~1.09 —— 两段区间是重叠的
# （「北京有哪些坑要注意？」0.904 vs 「珠海多玩一天怎么安排」0.912），
# 所以单靠阈值分不开，改为「先按城市元数据过滤，再卡一个较宽的阈值」。
MAX_DISTANCE = 1.2


@lru_cache(maxsize=1)
def _known_cities() -> tuple[str, ...]:
    """知识库覆盖的城市（取自文档的 city 元数据）。新增文档后需重启进程才会刷新。"""
    data = get_vector_store().get(include=["metadatas"])
    cities = {
        str(meta.get("city"))
        for meta in (data.get("metadatas") or [])
        if meta and meta.get("city")
    }
    return tuple(sorted(cities))


def retrieve_knowledge(query: str, top_k: int = 3):
    """只在问题里提到知识库覆盖的城市时才检索。

    这样问交通、问别的城市都不会被硬塞一座城市的内容进去；
    同义改写（「北京有哪些坑要注意」）因为城市对得上，仍然能命中。
    """
    cities = [city for city in _known_cities() if city in query]
    if not cities:
        return []

    results = get_vector_store().similarity_search_with_score(
        query, k=top_k, filter={"city": {"$in": cities}}
    )
    return [doc.page_content for doc, score in results if score < MAX_DISTANCE]
