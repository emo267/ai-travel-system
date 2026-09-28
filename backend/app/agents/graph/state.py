from typing import TypedDict, List, Dict, Optional, Any


class TravelAgentState(TypedDict):
    # 输入信息
    task_id: int
    destination: str
    start_date: str
    end_date: str
    people_num: int
    male_num: Optional[int]
    female_num: Optional[int]
    total_budget: Optional[float]
    hotel_preference: str
    travel_style: str
    traffic_type: str
    extra_require: str

    # 工具执行结果
    weather_data: Optional[Dict[str, Any]]
    poi_data: Optional[List[Dict[str, Any]]]
    research: Optional[str]              # 模型调用工具查到的实时数据笔记

    # Agent 规划结果
    route_plan: Optional[Dict[str, Any]]      # 交通路线 Agent 输出
    budget_plan: Optional[Dict[str, Any]]     # 预算核算工具输出
    itinerary: Optional[Dict[str, Any]]       # 最终生成的行程

    # 评审与重试
    review_feedback: Optional[List[str]]      # 值得重排一次的意见（为空即不重试）
    review_score: int                         # 合理性评分
    review_report: Optional[Dict[str, Any]]   # 评审模型输出（分数/说明/问题），供落库
    retry_count: int                          # 当前重试次数
    max_retries: int                          # 最大重试次数