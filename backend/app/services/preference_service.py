from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.chat_conversation import ChatConversation
from app.db.models.user_preference import UserPreference
from app.schemas.preference_schema import PreferenceIn


def _apply(
    preference: UserPreference,
    persona: str,
    custom_persona: str,
    answer_length: str,
    show_sources: bool,
) -> None:
    preference.persona = persona
    preference.custom_persona = custom_persona
    preference.answer_length = answer_length
    preference.show_sources = show_sources


def get_or_create_preference(db: Session, user_id: int) -> UserPreference:
    """取该账号的助手设置；还没有就按默认值建一条，保证每个账号各存一份"""
    preference = db.get(UserPreference, user_id)
    if preference:
        return preference
    preference = UserPreference(user_id=user_id)
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return preference


def update_preference(db: Session, user_id: int, data: PreferenceIn) -> UserPreference:
    preference = get_or_create_preference(db, user_id)
    _apply(
        preference,
        data.persona,
        data.custom_persona,
        data.answer_length,
        data.show_sources,
    )
    db.commit()
    db.refresh(preference)
    return preference


def sync_from_latest_conversation(db: Session, user_id: int) -> Optional[UserPreference]:
    """账号默认设置 = 该账号最新「创建」的会话的设置。

    让账号默认只随「新建会话」变化，而不随「翻出老会话改设置」变化，行为才稳定可预期。
    一条会话都没有就保持现状，不清零。调用方必须先 commit，否则未提交的改动
    （尤其是删除）对这里的查询不可见，会把刚删的会话又选回来。
    """
    latest = (
        db.query(ChatConversation)
        .filter(ChatConversation.user_id == user_id)
        # create_time 只精确到秒，同秒并列时用 id 兜底保证结果确定
        .order_by(ChatConversation.create_time.desc(), ChatConversation.conversation_id.desc())
        .first()
    )
    if latest is None:
        return None

    preference = get_or_create_preference(db, user_id)
    _apply(
        preference,
        latest.persona,
        latest.custom_persona,
        latest.answer_length,
        latest.show_sources,
    )
    db.commit()
    db.refresh(preference)
    return preference
