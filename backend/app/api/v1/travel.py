from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core import clock
from app.tasks.travel_tasks import generate_travel_plan_task
from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.travel_schema import (
    TravelPlanOut,
    TravelTaskCreate,
    TravelTaskDetail,
    TravelTaskOut,
    TravelTaskUpdate,
)
from app.services import travel_service

router = APIRouter(prefix="/travel", tags=["行程"])


def reject_past_start_date(start_date: date | None) -> None:
    """出发日期不能早于今天。

    「今天」按业务时区算而不是服务器日期：容器跑在 UTC，直接用 date.today() 的话
    东八区的 00:00-08:00 会少算一天，把昨天当成今天放过去。
    """
    if start_date is None:
        return
    today = clock.today()
    if start_date < today:
        raise HTTPException(
            status_code=400,
            detail=f"出发日期不能早于今天（{today.isoformat()}），请重新选择",
        )


@router.post("/tasks", response_model=TravelTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    task_in: TravelTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reject_past_start_date(task_in.start_date)
    if task_in.end_date < task_in.start_date:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")
    return travel_service.create_travel_task(db, current_user.user_id, task_in)


@router.get("/tasks", response_model=List[TravelTaskOut])
def list_tasks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return travel_service.get_travel_tasks(db, current_user.user_id, skip, limit)


@router.get("/tasks/{task_id}", response_model=TravelTaskDetail)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = travel_service.get_travel_task(db, current_user.user_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="行程任务不存在")

    detail = TravelTaskDetail.model_validate(task)
    plan = travel_service.get_travel_plan_by_task(db, task_id)
    if plan:
        detail.plan = TravelPlanOut.model_validate(plan)
    return detail


@router.put("/tasks/{task_id}", response_model=TravelTaskOut)
def update_task(
    task_id: int,
    task_in: TravelTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = travel_service.get_travel_task(db, current_user.user_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="行程任务不存在")
    # 只校验这次真的传了开始日期的请求；没传就沿用库里已有的值
    reject_past_start_date(task_in.start_date)
    return travel_service.update_travel_task(db, task, task_in)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = travel_service.get_travel_task(db, current_user.user_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="行程任务不存在")
    travel_service.delete_travel_task(db, task)
    return None


@router.post("/tasks/{task_id}/generate")
def trigger_generate(
        task_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """触发异步生成行程"""
    task = travel_service.get_travel_task(db, current_user.user_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="行程任务不存在")

    if task.status == "generating":
        raise HTTPException(status_code=400, detail="行程正在生成中，请勿重复提交")

    # 发送异步任务到 Celery
    generate_travel_plan_task.delay(task_id)

    # 立即更新状态，防止前端重复点击
    task.status = "generating"
    db.commit()

    return {"msg": "任务已提交，正在后台生成", "task_id": task_id}

@router.get("/tasks/{task_id}/status")
def get_task_status(
        task_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """查询任务生成状态"""
    task = travel_service.get_travel_task(db, current_user.user_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="行程任务不存在")

    # 如果已完成，顺带返回方案详情
    plan = travel_service.get_travel_plan_by_task(db, task_id)

    return {
        "task_id": task_id,
        "status": task.status,
        "plan": plan.itinerary if plan else None,
        "reason_score": plan.reason_score if plan else None
    }