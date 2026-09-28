from celery import Celery
from app.core.config import settings

# 使用 Redis 作为 Broker（消息队列）和 Backend（结果存储）
celery_app = Celery(
    "travel_planner",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.travel_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_time_limit=300,  # 单个任务最长5分钟
)