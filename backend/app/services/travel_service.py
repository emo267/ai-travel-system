from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models.chat_record import ChatRecord
from app.db.models.travel_plan import TravelPlan
from app.db.models.travel_task import TravelTask
from app.schemas.travel_schema import TravelTaskCreate, TravelTaskUpdate


def create_travel_task(db: Session, user_id: int, task_in: TravelTaskCreate) -> TravelTask:
    task = TravelTask(user_id=user_id, **task_in.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_travel_tasks(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> List[TravelTask]:
    return (
        db.query(TravelTask)
        .filter(TravelTask.user_id == user_id)
        .order_by(TravelTask.create_time.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_travel_task(db: Session, user_id: int, task_id: int) -> Optional[TravelTask]:
    return (
        db.query(TravelTask)
        .filter(TravelTask.task_id == task_id, TravelTask.user_id == user_id)
        .first()
    )


def update_travel_task(
    db: Session,
    task: TravelTask,
    task_in: TravelTaskUpdate,
) -> TravelTask:
    update_data = task_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


def delete_travel_task(db: Session, task: TravelTask) -> None:
    # travel_plan.task_id 是 NOT NULL 外键且没有级联，不先删方案的话，
    # ORM 删除任务时会试图把子表外键置空并抛完整性错误（前端表现为"数据库操作异常"）
    db.query(TravelPlan).filter(TravelPlan.task_id == task.task_id).delete(
        synchronize_session=False
    )
    # 聊天记录允许脱离行程存在（task_id 可空）：解绑保留历史，不跟着删
    db.query(ChatRecord).filter(ChatRecord.task_id == task.task_id).update(
        {"task_id": None}, synchronize_session=False
    )
    db.delete(task)
    db.commit()


def get_travel_plan_by_task(db: Session, task_id: int) -> Optional[TravelPlan]:
    return db.query(TravelPlan).filter(TravelPlan.task_id == task_id).first()