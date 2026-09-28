from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UtcDateTime


class TravelTaskCreate(BaseModel):
    destination: str = Field(..., max_length=100)
    start_date: date
    end_date: date
    people_num: int = Field(1, ge=1)
    male_num: Optional[int] = Field(None, ge=0)
    female_num: Optional[int] = Field(None, ge=0)
    total_budget: Optional[float] = None
    hotel_preference: Optional[str] = None
    travel_style: Optional[str] = None
    traffic_type: Optional[str] = None
    extra_require: Optional[str] = None


class TravelTaskUpdate(BaseModel):
    destination: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    people_num: Optional[int] = None
    male_num: Optional[int] = None
    female_num: Optional[int] = None
    total_budget: Optional[float] = None
    hotel_preference: Optional[str] = None
    travel_style: Optional[str] = None
    traffic_type: Optional[str] = None
    extra_require: Optional[str] = None
    status: Optional[str] = None


class TravelTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: int
    user_id: int
    destination: str
    start_date: date
    end_date: date
    people_num: int
    male_num: Optional[int]
    female_num: Optional[int]
    total_budget: Optional[float]
    hotel_preference: Optional[str]
    travel_style: Optional[str]
    traffic_type: Optional[str]
    extra_require: Optional[str]
    create_time: UtcDateTime
    status: str


class TravelPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    task_id: int
    total_days: Optional[int]
    total_cost: Optional[float]
    weather_summary: Optional[str]
    itinerary: Any
    reason_score: Optional[int]
    generate_time: UtcDateTime


class TravelTaskDetail(TravelTaskOut):
    plan: Optional[TravelPlanOut] = None