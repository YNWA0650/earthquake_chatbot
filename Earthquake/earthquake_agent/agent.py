from langgraph.graph import StateGraph, START, END

from earthquake_agent.utils.state import State
from earthquake_agent.utils.nodes import (
    supervisor_node,
    normaliser_node,
    executor_node,
    summariser_node,
    route_from_supervisor,
)

workflow = StateGraph(State)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("normaliser_agent", normaliser_node)
workflow.add_node("executor_agent", executor_node)
workflow.add_node("summariser_agent", summariser_node)

workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges(
    "supervisor",
    route_from_supervisor,
    {"normaliser": "normaliser_agent", END: END},
)
workflow.add_edge("normaliser_agent", "executor_agent")
workflow.add_edge("executor_agent", "summariser_agent")
workflow.add_edge("summariser_agent", END)

graph = workflow.compile()
