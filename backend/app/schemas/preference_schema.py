from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UtcDateTime

CUSTOM_PERSONA_LIMIT = 120


class PreferenceIn(BaseModel):
    """助手设置：前端侧面板的全部选项，缺省即默认值"""

    persona: Literal["professional", "humorous", "caring", "concise", "custom"] = "professional"
    custom_persona: str = Field(default="", max_length=CUSTOM_PERSONA_LIMIT)
    answer_length: Literal["short", "medium", "long"] = "medium"
    show_sources: bool = True


class PreferenceOut(PreferenceIn):
    model_config = ConfigDict(from_attributes=True)

    update_time: UtcDateTime
