from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ChatRecord(Base):
    __tablename__ = "chat_record"

    record_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="记录ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"), nullable=False, index=True, comment="所属用户")
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("chat_conversation.conversation_id"), nullable=False, index=True, comment="所属会话"
    )
    task_id: Mapped[int | None] = mapped_column(ForeignKey("travel_task.task_id"), nullable=True, index=True, comment="关联行程")
    role: Mapped[str] = mapped_column(String(10), nullable=False, comment="消息角色：user/assistant")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="发送时间")