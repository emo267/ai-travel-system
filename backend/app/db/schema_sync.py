import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TABLE = "chat_record"
COLUMN = "conversation_id"
INDEX = "ix_chat_record_conversation_id"
FK = "fk_chat_record_conversation"

# GET_LOCK 是 MySQL 连接级的，连接断开会自动释放，所以不需要额外的锁表
LOCK_NAME = "travel_system:schema_sync"
LOCK_TIMEOUT = 30


def sync_schema(engine: Engine) -> None:
    """启动时的幂等结构同步。

    create_all 只建「缺的表」，不会给已存在的表加列 —— chat_conversation 会被建出来，
    但老库的 chat_record 仍然没有 conversation_id，不补的话聊天写库直接报 Unknown column。

    DDL 必须和 GET_LOCK 走同一条连接；回填另开连接（见 _backfill），锁仍然有效。
    """
    with engine.connect() as conn:
        locked = conn.execute(
            text("SELECT GET_LOCK(:name, :timeout)"),
            {"name": LOCK_NAME, "timeout": LOCK_TIMEOUT},
        ).scalar()
        if not locked:
            logger.warning("[SchemaSync] 没抢到结构同步锁，跳过（另一个进程正在同步）")
            return
        try:
            _ensure_conversation_column(conn, engine)
        finally:
            # 释放失败不影响启动：连接关掉时 MySQL 会自动放锁
            try:
                conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME})
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[SchemaSync] 释放结构同步锁失败：%s", exc)


def _ensure_conversation_column(conn: Connection, engine: Engine) -> None:
    """把 chat_record.conversation_id 补齐，步骤全部可重复执行，中途挂掉下次接着跑。

    MySQL 8 单条 DDL 是原子的，但没法把「加列 + 回填 + 改约束」包进一个事务，
    所以设计成一串「看库里的实际情况再决定做不做」的幂等步骤。
    """
    inspector = inspect(conn)
    columns = {column["name"] for column in inspector.get_columns(TABLE)}

    if COLUMN not in columns:
        # 必须先用可空列 + 回填，最后再收紧 NOT NULL。
        # 直接 ADD COLUMN ... NOT NULL 的话，MySQL 会用隐式默认值 0 填满现有行，
        # 那 36 条老记录会全部指向不存在的会话 0。
        logger.info("[SchemaSync] %s 缺 %s，补列", TABLE, COLUMN)
        conn.execute(
            text(
                f"ALTER TABLE {TABLE} "
                f"ADD COLUMN {COLUMN} INT NULL COMMENT '所属会话', "
                f"ADD INDEX {INDEX} ({COLUMN})"
            )
        )
        conn.commit()
        inspector = inspect(conn)  # Inspector 会缓存元数据，DDL 之后必须重建

    if INDEX not in {index["name"] for index in inspector.get_indexes(TABLE)}:
        conn.execute(text(f"ALTER TABLE {TABLE} ADD INDEX {INDEX} ({COLUMN})"))
        conn.commit()
        inspector = inspect(conn)

    column = next(c for c in inspector.get_columns(TABLE) if c["name"] == COLUMN)
    if not column["nullable"]:
        # 新库，或已经同步过的老库：NOT NULL 列不可能含 NULL，这里必然是空转
        _ensure_foreign_key(conn, inspector)
        return

    _backfill(engine)

    remaining = conn.execute(
        text(f"SELECT COUNT(*) FROM {TABLE} WHERE {COLUMN} IS NULL")
    ).scalar()
    if remaining:
        logger.warning("[SchemaSync] 还有 %s 条聊天记录没归到会话，这次不收紧 NOT NULL", remaining)
        return

    conn.execute(
        text(f"ALTER TABLE {TABLE} MODIFY COLUMN {COLUMN} INT NOT NULL COMMENT '所属会话'")
    )
    conn.commit()
    logger.info("[SchemaSync] %s.%s 已收紧为 NOT NULL", TABLE, COLUMN)
    _ensure_foreign_key(conn, inspect(conn))


def _ensure_foreign_key(conn: Connection, inspector) -> None:
    # 按列名判断而不是按约束名：新库上 create_all 自己起的名是 chat_record_ibfk_2 这类
    has_fk = any(
        fk.get("constrained_columns") == [COLUMN] for fk in inspector.get_foreign_keys(TABLE)
    )
    if has_fk:
        return
    logger.info("[SchemaSync] 补 %s.%s 外键", TABLE, COLUMN)
    conn.execute(
        text(
            f"ALTER TABLE {TABLE} ADD CONSTRAINT {FK} "
            f"FOREIGN KEY ({COLUMN}) REFERENCES chat_conversation(conversation_id)"
        )
    )
    conn.commit()


def _backfill(engine: Engine) -> None:
    """回填老消息的会话归属。

    用独立连接和独立 Session：持有 DDL 连接的事务里混一个 Session 的 commit 很容易出意外，
    而锁在 DDL 连接上，另一个连接做事同样是互斥的。
    """
    from app.services import chat_service  # 局部 import，避免 main 加载期的循环依赖

    session = Session(engine)
    try:
        created = chat_service.backfill_conversations(session)
        if created:
            logger.info("[SchemaSync] 历史消息已归入 %s 个会话", created)
    finally:
        session.close()
