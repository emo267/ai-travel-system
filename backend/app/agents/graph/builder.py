from langgraph.graph import StateGraph, END
from app.agents.graph.state import TravelAgentState
from app.agents.master_agent import master_agent_node
from app.agents.route_agent import route_agent_node
from app.agents.review_agent import review_agent_node


def should_retry(state: TravelAgentState) -> str:
    """条件边：判断是否需要重试"""
    feedback = state.get("review_feedback", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if feedback and retry_count < max_retries:
        print(f"[Graph] 评审不通过，触发重试 ({retry_count}/{max_retries})")
        return "retry"
    print("[Graph] 评审通过或达到最大重试次数，结束流程")
    return "end"


def build_travel_graph():
    workflow = StateGraph(TravelAgentState)

    # 添加节点
    workflow.add_node("master", master_agent_node)
    workflow.add_node("route", route_agent_node)
    workflow.add_node("review", review_agent_node)

    # 设置入口
    workflow.set_entry_point("master")

    # 普通边
    workflow.add_edge("master", "route")
    workflow.add_edge("route", "review")

    # 条件边：评审后决定重试还是结束
    workflow.add_conditional_edges(
        "review",
        should_retry,
        {
            "retry": "master",  # 重试则回到主 Agent 重新生成
            "end": END
        }
    )

    return workflow.compile()

# 全局编译好的图实例
travel_graph = build_travel_graph()