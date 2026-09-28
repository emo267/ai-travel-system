from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserPreference(Base):
    __tablename__ = "user_preference"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        primary_key=True,
        comment="用户编号（一个账号一条设置）",
    )
    persona: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="professional",
        comment="助手性格：professional/humorous/caring/concise/custom",
    )
    custom_persona: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        comment="persona=custom 时的自定义风格要求",
    )
    answer_length: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        comment="回答长度：short/medium/long",
    )
    show_sources: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否显示知识库引用",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后更新时间",
    )
