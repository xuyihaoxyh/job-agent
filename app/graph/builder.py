from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.company import make_company_node
from app.graph.nodes.intake import make_intake_node
from app.graph.nodes.jd import make_jd_node
from app.graph.nodes.match import match_candidate
from app.graph.nodes.report import make_report_node
from app.graph.nodes.salary import make_salary_node
from app.graph.state import JobAnalysisState


def build_graph(
    dependencies: GraphDependencies,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
):
    builder = StateGraph(JobAnalysisState)
    builder.add_node("intake", make_intake_node(dependencies))
    builder.add_node("jd", make_jd_node(dependencies))
    builder.add_node("company", make_company_node(dependencies))
    builder.add_node("salary", make_salary_node(dependencies))
    builder.add_node("match", match_candidate)
    builder.add_node("report", make_report_node(dependencies))

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "jd")

    # Fixed fan-out: these nodes are independent once JD extraction finishes.
    builder.add_edge("jd", "company")
    builder.add_edge("jd", "salary")
    builder.add_edge("jd", "match")

    # Fan-in: report runs only after all three incoming branches finish.
    builder.add_edge("company", "report")
    builder.add_edge("salary", "report")
    builder.add_edge("match", "report")
    builder.add_edge("report", END)

    return builder.compile(checkpointer=checkpointer)

