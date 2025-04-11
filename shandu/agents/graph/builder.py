"""
Graph builder for research graph.
"""
from langgraph.graph import Graph, StateGraph
from ..processors.content_processor import AgentState
from ..utils.agent_utils import should_continue

def build_graph(
    initialize_node,
    reflect_node,
    generate_queries_node,
    search_node,
    smart_source_selection,
    format_citations_node,
    generate_initial_report_node,
    enhance_report_node,
    expand_key_sections_node,
    report_node
) -> Graph:
    """
    Build the research workflow graph with all nodes.
    
    Args:
        All node functions for the research graph
        
    Returns:
        Compiled graph ready for execution
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("initialize", initialize_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("generate_queries", generate_queries_node)
    workflow.add_node("search", search_node)
    workflow.add_node("smart_source_selection", smart_source_selection)
    workflow.add_node("format_citations", format_citations_node)
    workflow.add_node("generate_initial_report", generate_initial_report_node)
    workflow.add_node("enhance_report", enhance_report_node)
    workflow.add_node("expand_key_sections", expand_key_sections_node)
    workflow.add_node("report", report_node)

    workflow.add_edge("initialize", "generate_queries")
    workflow.add_edge("reflect", "generate_queries")
    workflow.add_edge("generate_queries", "search")
    workflow.add_conditional_edges("search", should_continue, {
        "continue": "reflect", 
        "end": "smart_source_selection"
    })

    workflow.add_edge("smart_source_selection", "format_citations")
    workflow.add_edge("format_citations", "generate_initial_report")
    workflow.add_edge("generate_initial_report", "enhance_report")
    workflow.add_edge("enhance_report", "expand_key_sections")
    workflow.add_edge("expand_key_sections", "report")
    
    workflow.set_entry_point("initialize")
    workflow.set_finish_point("report")
    
    return workflow.compile()