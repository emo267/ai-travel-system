from app.db.models.user import User
from app.db.models.user_preference import UserPreference
from app.db.models.travel_task import TravelTask
from app.db.models.travel_plan import TravelPlan
from app.db.models.chat_conversation import ChatConversation
from app.db.models.chat_record import ChatRecord

# create_all 只会建「已经 import 过」的表，所以模型必须在这里列全
__all__ = [
    "User",
    "UserPreference",
    "TravelTask",
    "TravelPlan",
    "ChatConversation",
    "ChatRecord",
]
