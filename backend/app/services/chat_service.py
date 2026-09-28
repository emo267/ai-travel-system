from datetime import timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.chat_conversation import ChatConversation
from app.db.models.chat_record import ChatRecord
from app.services import preference_service

# 会话标题取首条用户消息的前若干字
TITLE_LIMIT = 20
# 回填历史消息时，间隔超过这个时长就算另一轮对话
BACKFILL_GAP = timedelta(hours=2)


def make_title(text: str) -> str:
    """取消息开头做会话标题；压掉换行与连续空格，跟 resolve_style 的写法一致"""
    title = " ".join(str(text or "").split())
    return title[:TITLE_LIMIT] or "新对话"


def save_chat_record(
    db: Session,
    user_id: int,
    role: str,
    content: str,
    task_id: Optional[int] = None,
    *,
    conversation_id: int,
) -> ChatRecord:
    # conversation_id 做成关键字限定：现有调用都按位置传 task_id，
    # 不加 * 的话新参数会静默把 task_id 当成会话 id
    record = ChatRecord(
        user_id=user_id,
        conversation_id=conversation_id,
        task_id=task_id,
        role=role,
        content=content,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_conversation_messages(
    db: Session,
    conversation_id: int,
    limit: int = 200,
) -> List[ChatRecord]:
    """取会话内最近 limit 条消息，按时间正序返回（超长会话也要先看到最新的一段）"""
    records = (
        db.query(ChatRecord)
        .filter(ChatRecord.conversation_id == conversation_id)
        # create_time 只精确到秒，同秒的用 record_id 兜底保证顺序确定
        .order_by(ChatRecord.create_time.desc(), ChatRecord.record_id.desc())
        .limit(limit)
        .all()
    )
    records.reverse()
    return records


def _split_by_gap(records: List[ChatRecord], gap: timedelta) -> List[List[ChatRecord]]:
    """按消息时间间隔切分会话：相邻两条相隔超过 gap 就另起一段"""
    groups: List[List[ChatRecord]] = [[records[0]]]
    for previous, current in zip(records, records[1:]):
        if current.create_time - previous.create_time > gap:
            groups.append([current])
        else:
            groups[-1].append(current)
    return groups


def _title_source(group: List[ChatRecord]) -> str:
    """优先拿组里第一条用户消息当标题来源，整组没有用户消息才退回第一条"""
    for record in group:
        if record.role == "user":
            return record.content
    return group[0].content


def backfill_conversations(db: Session) -> int:
    """把还没有会话归属的历史消息按时间间隔补上会话，返回新建的会话数。

    只处理 conversation_id IS NULL 的行，所以第一次跑完后再启动就是空转。
    一个用户一个事务：中途挂掉整组回滚，下次重跑结果一致。
    """
    pending_user_ids = [
        row[0]
        for row in db.execute(
            select(ChatRecord.user_id).where(ChatRecord.conversation_id.is_(None)).distinct()
        )
    ]

    created = 0
    for user_id in pending_user_ids:
        records = (
            db.query(ChatRecord)
            .filter(ChatRecord.user_id == user_id, ChatRecord.conversation_id.is_(None))
            .order_by(ChatRecord.create_time.asc(), ChatRecord.record_id.asc())
            .all()
        )
        if not records:
            continue

        preference = preference_service.get_or_create_preference(db, user_id)
        for group in _split_by_gap(records, BACKFILL_GAP):
            conversation = ChatConversation(
                user_id=user_id,
                title=make_title(_title_source(group)),
                persona=preference.persona,
                custom_persona=preference.custom_persona,
                answer_length=preference.answer_length,
                show_sources=preference.show_sources,
                # 会话时间取组内第一条消息，列表里的时间才有意义
                create_time=group[0].create_time,
            )
            db.add(conversation)
            db.flush()  # 拿到 conversation_id
            for record in group:
                record.conversation_id = conversation.conversation_id
            created += 1
        db.commit()

    return created
