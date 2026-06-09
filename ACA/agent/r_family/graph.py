"""R-family LangGraph state graph.

Graph structure:
  agent ──(run_and_trace)──> tools ──> agent (loop)
    │                            │
    └──(terminal condition)──────┴──> finalize → END
"""

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from ACA.agent.r_family.config import R1Config
from ACA.agent.shared.state import AgentState


def _make_finalize_node(config: R1Config):
    """Return a finalize_node that sets termination reason."""

    def finalize_node(state: AgentState) -> Dict[str, Any]:
        if state.get("terminated_reason"):
            return {}

        uncovered = state.get("uncovered_lines", [])

        if len(uncovered) == 0:
            return {"terminated_reason": "all_covered"}

        if state.get("iteration", 0) >= config.max_iterations:
            return {"terminated_reason": "max_iterations"}
        if state.get("stagnation_counter", 0) >= config.patience:
            return {"terminated_reason": "stagnation"}
        # 10 consecutive LLM responses without tool calls → agent lost, bail out
        if state.get("no_tool_call_count", 0) >= config.no_tool_call_limit:
            return {"terminated_reason": "agent_stopped"}

        messages = state.get("messages", [])
        if messages:
            last = messages[-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                name = last.tool_calls[0]["name"]
                return {"terminated_reason": f"unhandled_tool:{name}"}

        return {"terminated_reason": "unknown"}

    return finalize_node


def _make_router(config: R1Config):
    """Return a router function that decides next node after agent/tools."""

    def router(state: AgentState) -> str:
        if state.get("iteration", 0) >= config.max_iterations:
            return "finalize"
        if state.get("stagnation_counter", 0) >= config.patience:
            return "finalize"
        # 10 consecutive LLM responses without tool calls → agent lost, bail out
        if state.get("no_tool_call_count", 0) >= config.no_tool_call_limit:
            return "finalize"

        if state.get("terminated_reason"):
            return "finalize"

        messages = state.get("messages", [])
        if not messages:
            return "finalize"

        last = messages[-1]
        if not hasattr(last, "tool_calls") or not last.tool_calls:
            return "agent"  # LLM didn't call a tool → retry

        name = last.tool_calls[0]["name"]
        if name in {"run_and_trace", "run_generator_and_trace"}:
            return "tools"
        return "tools"  # unknown tools → tools node produces error message

    return router


def build_graph(config: R1Config, agent_node_fn, tool_executor_node_fn):
    """Build and compile the R-family LangGraph state graph."""
    builder = StateGraph(AgentState)

    builder.add_node("agent", agent_node_fn)
    builder.add_node("tools", tool_executor_node_fn)
    builder.add_node("finalize", _make_finalize_node(config))

    builder.set_entry_point("agent")

    router_fn = _make_router(config)

    builder.add_conditional_edges(
        "agent",
        router_fn,
        {
            "agent": "agent",
            "tools": "tools",
            "finalize": "finalize",
        },
    )

    builder.add_conditional_edges(
        "tools",
        router_fn,
        {
            "agent": "agent",
            "tools": "tools",
            "finalize": "finalize",
        },
    )

    builder.add_edge("finalize", END)

    return builder.compile()
