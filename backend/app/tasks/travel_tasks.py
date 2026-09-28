import time
from datetime import timedelta

from app.tasks.celery_app import celery_app
from app.db.session import SessionLocal
from app.db.models.travel_task import TravelTask
from app.db.models.travel_plan import TravelPlan
from app.agents.graph.builder import travel_graph


@celery_app.task(bind=True, max_retries=3)
def generate_travel_plan_task(self, task_id: int):
    db = SessionLocal()
    try:
        task = db.query(TravelTask).filter(TravelTask.task_id == task_id).first()
        if not task:
            return {"status": "failed", "msg": "任务不存在"}

        task.status = "generating"
        db.commit()

        # 1. 构建初始 State
        initial_state = {
            "task_id": task.task_id,
            "destination": task.destination,
            "start_date": str(task.start_date),
            "end_date": str(task.end_date),
            "people_num": task.people_num,
            "male_num": task.male_num,
            "female_num": task.female_num,
            # 空预算就是"不限制"，不再兜底成 5000（否则会和创建页的"留空表示不限制"矛盾）
            "total_budget": float(task.total_budget) if task.total_budget else None,
            # 空值代表用户的选择（不订住宿 / 不限），不能兜底成具体偏好，否则会篡改用户意图
            "hotel_preference": task.hotel_preference or "不安排住宿",
            "travel_style": task.travel_style or "不限",
            "traffic_type": task.traffic_type or "不限",
            "extra_require": task.extra_require or "",
            "weather_data": None,
            "poi_data": None,
            "research": None,
            "route_plan": None,
            "budget_plan": None,
            "itinerary": None,
            "review_feedback": [],
            "review_score": 100,
            "review_report": None,
            "retry_count": 0,
            "max_retries": 3
        }

        # 2. 运行 LangGraph
        final_state = travel_graph.invoke(initial_state)

        # 3. 提取结果并写入数据库
        itinerary = final_state.get("itinerary", {})
        weather_data = final_state.get("weather_data") or {}
        weather_summary = weather_data.get("summary", "")
        forecast = weather_data.get("forecast") or []
        budget_plan = final_state.get("budget_plan") or {}
        total_cost = budget_plan.get("total_cost", 0)
        reason_score = final_state.get("review_score", 100)

        # 预算口径与档位对比随行程一起落库，供详情页展示（itinerary 是 JSON 列，不用改表）
        if budget_plan:
            itinerary = {
                **itinerary,
                "budget": {
                    "basis": budget_plan.get("basis"),
                    "upsell": budget_plan.get("upsell"),
                    "breakdown": budget_plan.get("breakdown"),
                    "suggestion": budget_plan.get("suggestion"),
                    "rooms": budget_plan.get("rooms"),
                    "nights": budget_plan.get("nights"),
                },
            }

        # 逐日预报一并落库，详情页按天展示；给每天补上日期，前端据此把天气与日程对齐
        if forecast:
            itinerary = {
                **itinerary,
                "weather": forecast,
                "weather_advice": weather_data.get("advice") or "",
            }

        # 联网调研笔记一并落库，详情页可展开查看价格来源（可审计）
        research = final_state.get("research") or ""
        if research:
            itinerary = {**itinerary, "research": research}

        # 评审说明一并落库（itinerary 是 JSON 列，不用改表）；
        # needs_regeneration 只是流程信号，不落库
        review_report = final_state.get("review_report") or {}
        if review_report:
            itinerary = {
                **itinerary,
                "review": {
                    "score": review_report.get("score"),
                    "summary": review_report.get("summary") or "",
                    "explanation": review_report.get("explanation") or "",
                    "dimensions": review_report.get("dimensions") or [],
                    "suggestions": review_report.get("suggestions") or [],
                    "issues": review_report.get("issues") or [],
                },
            }

        for index, day in enumerate(itinerary.get("days") or []):
            day.setdefault("date", (task.start_date + timedelta(days=index)).isoformat())

        # 清理旧方案
        db.query(TravelPlan).filter(TravelPlan.task_id == task_id).delete()

        plan = TravelPlan(
            task_id=task_id,
            total_days=(task.end_date - task.start_date).days + 1,
            total_cost=total_cost,
            weather_summary=weather_summary,
            itinerary=itinerary,
            reason_score=reason_score
        )
        db.add(plan)
        task.status = "completed"
        db.commit()

        return {"status": "success", "task_id": task_id}

    except Exception as exc:
        db.rollback()
        task = db.query(TravelTask).filter(TravelTask.task_id == task_id).first()
        if task:
            task.status = "failed"
            db.commit()
        raise self.retry(exc=exc, countdown=5)
    finally:
        db.close()