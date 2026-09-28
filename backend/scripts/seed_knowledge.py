from app.rag.knowledge_loader import load_knowledge
from app.rag.vector_store import get_vector_store


def reset_collection():
    """先清空再入库，保证脚本可以反复执行（否则每次都会重复追加）"""
    store = get_vector_store()
    store.delete_collection()
    print("已清空知识库 collection")


def seed():
    reset_collection()

    docs = [
        {
            "title": "北京旅行攻略",
            "category": "攻略",
            "city": "北京",
            "content": "北京必去景点：故宫博物院、天安门广场、八达岭长城、颐和园、天坛公园、南锣鼓巷。"
                       "推荐美食：北京烤鸭、老北京炸酱面、卤煮火烧、铜锅涮肉。"
                       "交通以地铁为主，线路密集、票价便宜，早晚高峰非常拥挤，建议错峰出行。",
        },
        {
            "title": "北京避雷指南",
            "category": "避雷",
            "city": "北京",
            "content": "故宫、国家博物馆、天安门广场都要提前在官方渠道实名预约，热门时段常常提前几天就约满。"
                       "长城建议去八达岭或慕田峪并从官方渠道购票，不要参加路边的低价一日游。"
                       "王府井小吃街价格偏高、口味一般，本地人更推荐牛街和簋街。",
        },
    ]
    for doc in docs:
        # city 元数据供检索时按城市过滤，新增城市时记得一并填上
        count = load_knowledge(
            doc["content"],
            {"title": doc["title"], "category": doc["category"], "city": doc["city"]},
        )
        print(f"已入库 {doc['title']}，共 {count} 个分块")


if __name__ == "__main__":
    seed()
