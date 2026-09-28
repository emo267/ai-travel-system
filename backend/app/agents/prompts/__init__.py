"""各 Agent 的提示词集中管理。

- 固定文案：模块常量（全大写），直接引用；
- 带变量的文案：模块级函数，参数只收普通值，不接收 state / DB 对象，
  方便脱离 Agent 单独测试；
- 跨 Agent 共用的片段（如简体中文约束）仍放在 app/llm/prompts.py，这里按需转发。

新增提示词请写进对应模块，不要再散落在 Agent 里。
"""

from app.agents.prompts.master_prompts import (
    RESEARCH_SUMMARY_PROMPT,
    RESEARCH_SYSTEM_PROMPT,
    itinerary_prompt,
    price_hints_prompt,
    research_kickoff_prompt,
)
from app.agents.prompts.review_prompts import REVIEW_SYSTEM_PROMPT, review_user_prompt
from app.agents.prompts.route_prompts import ROUTE_EXPERT_PROMPT, route_day_prompt

__all__ = [
    # 主规划师：调研员 / 价格抽取 / 行程生成
    "RESEARCH_SYSTEM_PROMPT",
    "research_kickoff_prompt",
    "RESEARCH_SUMMARY_PROMPT",
    "price_hints_prompt",
    "itinerary_prompt",
    # 路线 Agent
    "ROUTE_EXPERT_PROMPT",
    "route_day_prompt",
    # 评审 Agent
    "REVIEW_SYSTEM_PROMPT",
    "review_user_prompt",
]
