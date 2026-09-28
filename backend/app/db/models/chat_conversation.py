from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatConversation(Base):
    __tablename__ = "chat_conversation"

    conversation_id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="会话ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"), nullable=False, index=True, comment="所属用户"
    )
    title: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="会话标题（首条用户消息截断）"
    )

    # 下面 4 列与 user_preference 同名但语义不同：这里是「本会话」的设置，
    # user_preference 是「账号默认」设置（= 最新会话的设置）。
    # 类型与默认值必须和 user_preference 保持一致，否则两边会各存一份不同的值。
    persona: Mapped[str] = mapped_column(
        String(20), nullable=False, default="professional", comment="本会话助手性格"
    )
    custom_persona: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", comment="本会话自定义风格"
    )
    answer_length: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", comment="本会话回答长度"
    )
    show_sources: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="本会话是否显示引用"
    )

    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="会话创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后更新时间",
    )
