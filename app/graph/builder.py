from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.company import make_company_node
from app.graph.nodes.intake import make_intake_node
from app.graph.nodes.jd import make_jd_node
from app.graph.nodes.match import match_candidate
from app.graph.nodes.planner import make_planner_node, route_planned_agents
from app.graph.nodes.report import make_report_node
from app.graph.nodes.salary import make_salary_node
from app.graph.nodes.supervisor import make_supervisor_node, route_from_supervisor
from app.graph.state import JobAnalysisState


def route_fixed_agents(state: JobAnalysisState) -> list[str]:
    """Deterministically dispatch the user-selected V1 business nodes."""
    return list(
        dict.fromkeys(
            state.get("analysis_targets") or ["company", "salary", "match"]
        )
    )


def build_graph(
    dependencies: GraphDependencies,
    *,
    router_mode: str = "fixed",
    checkpointer: BaseCheckpointSaver | None = None,
):
    if router_mode not in {"fixed", "llm", "hybrid"}:
        raise ValueError(f"Unsupported router mode: {router_mode}")
    builder = StateGraph(JobAnalysisState)
    builder.add_node("intake", make_intake_node(dependencies))
    builder.add_node("jd", make_jd_node(dependencies))
    builder.add_node("company", make_company_node(dependencies))
    builder.add_node("salary", make_salary_node(dependencies))
    builder.add_node("match", match_candidate)
    builder.add_node("report", make_report_node(dependencies))

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "jd")

    if router_mode == "fixed":
        # Fixed fan-out: code dispatches exactly the user-selected independent nodes.
        builder.add_conditional_edges(
            "jd",
            route_fixed_agents,
            {"company": "company", "salary": "salary", "match": "match"},
        )

        # Fan-in: report runs only after all three incoming branches finish.
        builder.add_edge("company", "report")
        builder.add_edge("salary", "report")
        builder.add_edge("match", "report")
    elif router_mode == "llm":
        builder.add_node("supervisor", make_supervisor_node(dependencies))
        builder.add_edge("jd", "supervisor")
        builder.add_conditional_edges(
            "supervisor",
            route_from_supervisor,
            {
                "company": "company",
                "salary": "salary",
                "match": "match",
                "report": "report",
            },
        )
        builder.add_edge("company", "supervisor")
        builder.add_edge("salary", "supervisor")
        builder.add_edge("match", "supervisor")
    else:
        builder.add_node("planner", make_planner_node(dependencies))
        builder.add_edge("jd", "planner")
        builder.add_conditional_edges(
            "planner",
            route_planned_agents,
            {
                "company": "company",
                "salary": "salary",
                "match": "match",
            },
        )
        builder.add_edge("company", "report")
        builder.add_edge("salary", "report")
        builder.add_edge("match", "report")
    builder.add_edge("report", END)

    return builder.compile(checkpointer=checkpointer)
