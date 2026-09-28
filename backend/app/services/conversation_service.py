from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.chat_conversation import ChatConversation
from app.db.models.chat_record import ChatRecord
from app.schemas.chat_schema import ChatRequest, ConversationUpdate
from app.services import preference_service


def list_conversations(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> List[Tuple[ChatConversation, int, Optional[datetime]]]:
    """列出会话，附带消息数与最后一条消息时间。

    按「最近活跃」倒序而不是创建时间：继续聊过的老会话应该浮上来。
    这里不能用 chat_conversation.update_time —— 加消息时没人碰会话行，它不会动。
    """
    last_message = func.max(ChatRecord.create_time)
    return (
        db.query(ChatConversation, func.count(ChatRecord.record_id), last_message)
        .outerjoin(
            ChatRecord,
            ChatRecord.conversation_id == ChatConversation.conversation_id,
        )
        .filter(ChatConversation.user_id == user_id)
        .group_by(ChatConversation.conversation_id)
        .order_by(
            func.coalesce(last_message, ChatConversation.create_time).desc(),
            ChatConversation.conversation_id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_conversation(
    db: Session,
    user_id: int,
    conversation_id: int,
) -> Optional[ChatConversation]:
    """缺失与不属于当前用户一律当作不存在，接口层统一回 404、不区分"""
    return (
        db.query(ChatConversation)
        .filter(
            ChatConversation.conversation_id == conversation_id,
            ChatConversation.user_id == user_id,
        )
        .first()
    )


def create_conversation(
    db: Session,
    user_id: int,
    title: str,
    seed: Optional[ChatRequest] = None,
) -> ChatConversation:
    """新建会话，设置从「账号默认」继承（不读最新会话，否则刚存的账号设置会被丢弃）。

    seed 是本次发消息带的设置：persona 等非空时以它为准，正好补上
    「设置改动还没到防抖时间就发了消息」这个空档；show_sources 不在请求体里，
    一律取账号设置。
    """
    preference = preference_service.get_or_create_preference(db, user_id)
    conversation = ChatConversation(
        user_id=user_id,
        title=title,
        persona=(seed.persona if seed and seed.persona else preference.persona),
        custom_persona=(
            seed.custom_persona if seed and seed.custom_persona is not None else preference.custom_persona
        ),
        answer_length=(seed.answer_length if seed and seed.answer_length else preference.answer_length),
        show_sources=preference.show_sources,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    # 新行按定义就是最新创建的那个，重算一次等于重申不变式
    preference_service.sync_from_latest_conversation(db, user_id)
    return conversation


def update_conversation(
    db: Session,
    conversation: ChatConversation,
    payload: ConversationUpdate,
) -> ChatConversation:
    updates = payload.model_dump(exclude_unset=True)
    # title 是可空字段，不能把 None 写进 NOT NULL 列
    title = (updates.pop("title", None) or "").strip()
    if title:
        conversation.title = title[:100]
    for field, value in updates.items():
        setattr(conversation, field, value)
    db.commit()
    db.refresh(conversation)
    # 无条件重算：改的是老会话时，重算会找到最新那个并写回它没变的值，是无害的 no-op
    preference_service.sync_from_latest_conversation(db, conversation.user_id)
    return conversation


def delete_conversation(db: Session, conversation: ChatConversation) -> None:
    # commit 之后这个实例就是已删除状态、属性会过期，先把 user_id 取出来
    user_id = conversation.user_id

    # chat_record.conversation_id 是 NOT NULL 外键且没有级联，不先删子行的话
    # ORM 会试图把外键置空并抛完整性错误（同 travel_service.delete_travel_task 的坑）
    db.query(ChatRecord).filter(
        ChatRecord.conversation_id == conversation.conversation_id
    ).delete(synchronize_session=False)
    db.delete(conversation)
    # 必须先提交：SessionLocal 是 autoflush=False，未提交的删除对下面的重算查询不可见，
    # 会把刚删掉的会话又选回来当「最新会话」
    db.commit()
    preference_service.sync_from_latest_conversation(db, user_id)
