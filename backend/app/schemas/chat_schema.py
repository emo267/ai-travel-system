from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UtcDateTime
from app.schemas.preference_schema import CUSTOM_PERSONA_LIMIT, PreferenceIn


class ChatRequest(BaseModel):
    message: str
    task_id: Optional[int] = None  # 关联行程（可选）
    conversation_id: Optional[int] = None  # 为空表示「这是新会话的第一条消息」
    # 下面三个会随新会话落库，所以在这里就用字面量卡住：存进非法值的话，
    # 下次打开这个会话时设置面板会一个选项都选不中
    persona: Optional[Literal["professional", "humorous", "caring", "concise", "custom"]] = None
    custom_persona: Optional[str] = Field(default=None, max_length=CUSTOM_PERSONA_LIMIT)
    answer_length: Optional[Literal["short", "medium", "long"]] = None


class ChatRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: int
    user_id: int
    conversation_id: int
    task_id: Optional[int]
    role: str
    content: str
    create_time: UtcDateTime


class ConversationUpdate(PreferenceIn):
    """会话级设置 + 重命名；全部可选，只改传来的字段（沿用 TravelTaskUpdate 的写法）"""

    title: Optional[str] = Field(default=None, max_length=100)


class ConversationOut(PreferenceIn):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: int
    user_id: int
    title: str
    create_time: UtcDateTime
    update_time: UtcDateTime
    message_count: int = 0
    last_message_time: Optional[UtcDateTime] = None
