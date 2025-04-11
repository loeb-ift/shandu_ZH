"""
Citation formatting node for research graph with advanced tracking capabilities.
"""
import time
from rich.console import Console
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState
from ..processors.report_generator import format_citations
from ..utils.agent_utils import log_chain_of_thought, _call_progress_callback
from ..utils.citation_manager import CitationManager, SourceInfo
from ..utils.citation_registry import CitationRegistry

console = Console()

class FormattedCitations(BaseModel):
    """Structured output for formatted citations."""
    citations: list[str] = Field(
        description="List of properly formatted citations",
        min_items=1
    )

async def format_citations_node(llm, progress_callback, state: AgentState) -> AgentState:
    """
    Format citations for selected sources to ensure consistent referencing.
    
    This enhanced version uses the new CitationManager to track relationships
    between sources and specific learnings from them.
    """
    state["status"] = "Processing and formatting citations"
    console.print("[bold blue]Processing source citations with enhanced attribution...[/]")

    selected_urls = state["selected_sources"]
    if not selected_urls:
        log_chain_of_thought(state, "No sources selected for citations")
        return state

    if "citation_manager" not in state:
        state["citation_manager"] = CitationManager()
        # For backward compatibility
        state["citation_registry"] = state["citation_manager"].citation_registry
    
    citation_manager = state["citation_manager"]
    
    # Register each source with the citation manager
    for url in selected_urls:

        source_meta = next((s for s in state["sources"] if s.get("url") == url), {})

        source_info = SourceInfo(
            url=url,
            title=source_meta.get("title", ""),
            snippet=source_meta.get("snippet", ""),
            source_type="web",
            content_type=source_meta.get("content_type", "article"),
            access_time=time.time(),
            domain=url.split("//")[1].split("/")[0] if "//" in url else "unknown",
            reliability_score=0.8,  # Default score, could be more dynamic
            metadata=source_meta
        )

        citation_manager.add_source(source_info)
        
        # For backward compatibility, also register with citation registry
        citation_id = citation_manager.citation_registry.register_citation(url)
        citation_manager.citation_registry.update_citation_metadata(citation_id, {
            "title": source_meta.get("title", ""),
            "url": url,
            "snippet": source_meta.get("snippet", ""),
            "source": source_meta.get("source", "")
        })

    formatted_citations = await format_citations(
        llm, 
        selected_urls, 
        state["sources"], 
        citation_registry=citation_manager.citation_registry
    )
    
    state["formatted_citations"] = formatted_citations
    log_chain_of_thought(state, f"Processed and formatted citations for {len(selected_urls)} sources")
    
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state