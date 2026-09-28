from datetime import date, datetime

from sqlalchemy import Date, DateTime, DECIMAL, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TravelTask(Base):
    __tablename__ = "travel_task"

    task_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="任务ID")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
        index=True,
        comment="所属用户",
    )
    destination: Mapped[str] = mapped_column(String(100), nullable=False, comment="旅行目的地")
    start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="出行开始日期")
    end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="出行结束日期")
    people_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="出行人数")
    male_num: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="男性人数")
    female_num: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="女性人数")
    total_budget: Mapped[float | None] = mapped_column(DECIMAL(10, 2), nullable=True, comment="预算总额")
    hotel_preference: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="住宿偏好（多选，、分隔；空=不安排住宿）"
    )
    travel_style: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="游玩风格（多选，、分隔）"
    )
    traffic_type: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="交通方式（多选，、分隔）"
    )
    extra_require: Mapped[str | None] = mapped_column(Text, nullable=True, comment="个性化额外需求")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="任务创建时间",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="任务状态：pending/generating/completed/failed",
    )

    plan = relationship("TravelPlan", back_populates="task", uselist=False)