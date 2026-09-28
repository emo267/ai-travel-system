from datetime import datetime

from sqlalchemy import DateTime, DECIMAL, ForeignKey, Integer, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TravelPlan(Base):
    __tablename__ = "travel_plan"

    plan_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="方案ID")
    task_id: Mapped[int] = mapped_column(
        ForeignKey("travel_task.task_id"),
        nullable=False,
        unique=True,
        index=True,
        comment="对应行程任务",
    )
    total_days: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="总旅行天数")
    total_cost: Mapped[float | None] = mapped_column(DECIMAL(10, 2), nullable=True, comment="实际总花费")
    weather_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="行程天气总览")
    itinerary: Mapped[dict] = mapped_column(JSON, nullable=False, comment="每日行程结构化详情")
    reason_score: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="行程合理性评分")
    generate_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="方案生成时间",
    )

    task = relationship("TravelTask", back_populates="plan")