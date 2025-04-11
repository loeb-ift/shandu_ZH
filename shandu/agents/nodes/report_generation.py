"""Report generation nodes."""
import re
import time
import asyncio
from rich.console import Console
from rich.markdown import Markdown
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState
from ..processors.report_generator import (
    generate_title, 
    extract_themes, 
    generate_initial_report,
    enhance_report,
    expand_key_sections,
    format_citations
)
from ..utils.agent_utils import log_chain_of_thought, _call_progress_callback, is_shutdown_requested
from ..utils.citation_registry import CitationRegistry
from ..utils.citation_manager import CitationManager, SourceInfo, Learning

console = Console()

# Structured output models for report generation
class ReportSection(BaseModel):
    """Structured output for a report section."""
    title: str = Field(description="Title of the section")
    content: str = Field(description="Content of the section")

class FinalReport(BaseModel):
    """Structured output for the final report."""
    title: str = Field(description="Title of the report")
    sections: list[ReportSection] = Field(
        description="List of report sections",
        min_items=1
    )
    references: list[str] = Field(
        description="List of references in the report",
        min_items=0
    )

async def generate_initial_report_node(llm, include_objective, progress_callback, state: AgentState) -> AgentState:
    """Generate the initial report with enhanced citation tracking."""
    state["status"] = "Generating initial report with enhanced source attribution"
    console.print("[bold blue]Generating comprehensive report with dynamic structure and source tracking...[/]")

    current_date = state["current_date"]

    if "citation_manager" not in state:
        citation_manager = CitationManager()
        state["citation_manager"] = citation_manager
        # For backward compatibility
        state["citation_registry"] = citation_manager.citation_registry
    else:
        citation_manager = state["citation_manager"]

    citation_registry = citation_manager.citation_registry
    
    # Pre-register all selected sources and extract learnings
    if "selected_sources" in state and state["selected_sources"]:
        for url in state["selected_sources"]:

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

            for analysis in state["content_analysis"]:
                if url in analysis.get("sources", []):

                    citation_manager.extract_learning_from_text(
                        analysis.get("analysis", ""), 
                        url,
                        context=f"Analysis for query: {analysis.get('query', '')}"
                    )
            
            # For backward compatibility with citation registry
            cid = citation_registry.register_citation(url)
            citation_registry.update_citation_metadata(cid, {
                "title": source_meta.get("title", "Untitled"),
                "date": source_meta.get("date", "n.d."),
                "url": url
            })

    report_title = await generate_title(llm, state['query'])
    console.print(f"[bold green]Generated title: {report_title}[/]")

    extracted_themes = await extract_themes(llm, state['findings'])

    citation_stats = citation_manager.get_learning_statistics()
    console.print(f"[bold green]Processed {citation_stats.get('total_learnings', 0)} learnings from {citation_stats.get('total_sources', 0)} sources[/]")

    formatted_citations = await format_citations(
        llm, 
        state.get('selected_sources', []), 
        state["sources"],
        citation_registry  # For compatibility with format_citations function
    )

    initial_report = await generate_initial_report(
        llm,
        state['query'],
        state['findings'],
        extracted_themes,
        report_title,
        state['selected_sources'],
        formatted_citations,
        current_date,
        state['detail_level'],
        include_objective,
        citation_registry  # For compatibility with existing function
    )
    
    # Store the themes for later expansion steps
    state["identified_themes"] = extracted_themes
    state["initial_report"] = initial_report
    state["formatted_citations"] = formatted_citations
    
    log_chain_of_thought(
        state, 
        f"Generated initial report with {len(citation_registry.citations)} properly tracked citations and {citation_stats.get('total_learnings', 0)} learnings"
    )
    
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state

async def enhance_report_node(llm, progress_callback, state: AgentState) -> AgentState:
    """
    Skip enhancement step to avoid duplicating content - this function now
    just passes through the initial report to maintain pipeline compatibility.
    """

    if is_shutdown_requested():
        state["status"] = "Shutdown requested, skipping report enhancement"
        log_chain_of_thought(state, "Shutdown requested, skipping report enhancement")
        return state
    
    # Simply use the initial report without enhancement to avoid duplication issues
    state["enhanced_report"] = state["initial_report"]
    state["status"] = "Enhancement step skipped to preserve report structure"
    log_chain_of_thought(state, "Enhancement step skipped to preserve report structure")
    
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state

async def expand_key_sections_node(llm, progress_callback, state: AgentState) -> AgentState:
    """
    Skip expansion step to avoid duplicating content - this function now
    just passes through the initial report to maintain pipeline compatibility.
    """

    if is_shutdown_requested():
        state["status"] = "Shutdown requested, skipping section expansion"
        log_chain_of_thought(state, "Shutdown requested, skipping section expansion")
        return state
    
    # Simply use the enhanced report (which is the initial report) without expansion
    state["final_report"] = state["enhanced_report"]
    state["status"] = "Expansion step skipped to preserve report structure"
    log_chain_of_thought(state, "Expansion step skipped to preserve report structure")
    
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state

async def report_node(llm, progress_callback, state: AgentState) -> AgentState:
    """Finalize the report."""
    state["status"] = "Finalizing report"
    console.print("[bold blue]Research complete. Finalizing report...[/]")

    has_report = False
    if "final_report" in state and state["final_report"]:
        final_report = state["final_report"]
        has_report = True
    elif "enhanced_report" in state and state["enhanced_report"]:
        final_report = state["enhanced_report"]
        has_report = True
    elif "initial_report" in state and state["initial_report"]:
        final_report = state["initial_report"]
        has_report = True
    
    # If we have a report but it's broken or too short, regenerate it
    if has_report and (len(final_report.strip()) < 1000):
        console.print("[bold yellow]Existing report appears broken or incomplete. Regenerating...[/]")
        has_report = False
        
    # If we don't have a report, regenerate initial, enhanced, and expanded reports
    if not has_report:
        console.print("[bold yellow]No valid report found. Regenerating report from scratch...[/]")

        report_title = await generate_title(llm, state['query'])
        console.print(f"[bold green]Generated title: {report_title}[/]")

        extracted_themes = await extract_themes(llm, state['findings'])

        initial_report = await generate_initial_report(
            llm,
            state['query'],
            state['findings'],
            extracted_themes,
            report_title,
            state['selected_sources'],
            state.get('formatted_citations', ''),
            state['current_date'],
            state['detail_level'],
            False, # Don't include objective in fallback
            state.get('citation_registry') # Use existing citation registry if available
        )
        
        # Store the initial report
        state["initial_report"] = initial_report
        
        # Skip enhancement and expansion steps to maintain consistent report structure
        enhanced_report = initial_report
        state["enhanced_report"] = enhanced_report
        
        # Use the initial report directly as the final report
        final_report = initial_report

        used_source_urls = []
        for analysis in state["content_analysis"]:
            if "sources" in analysis and isinstance(analysis["sources"], list):
                for url in analysis["sources"]:
                    if url not in used_source_urls:
                        used_source_urls.append(url)
        
        # If we don't have enough used sources, also grab from selected_sources
        if len(used_source_urls) < 5 and "selected_sources" in state:
            for url in state["selected_sources"]:
                if url not in used_source_urls:
                    used_source_urls.append(url)
                    if len(used_source_urls) >= 15:
                        break

        sources_info = []
        for url in used_source_urls[:20]:  # Limit to 20 sources
            source_meta = next((s for s in state["sources"] if s.get("url") == url), {})
            sources_info.append({
                "url": url,
                "title": source_meta.get("title", ""),
                "snippet": source_meta.get("snippet", "")
            })

    # Apply comprehensive cleanup of artifacts and unwanted sections
    final_report = re.sub(r'Completed:.*?\n', '', final_report)
    final_report = re.sub(r'Here are.*?(search queries|queries to investigate).*?\n', '', final_report)
    final_report = re.sub(r'Generated search queries:.*?\n', '', final_report)
    final_report = re.sub(r'\*Generated on:.*?\*', '', final_report)
    
    # Remove "Refined Research Query" section which sometimes appears at the beginning
    final_report = re.sub(r'#\s*Refined Research Query:.*?(?=\n#|\Z)', '', final_report, flags=re.DOTALL)
    final_report = re.sub(r'Refined Research Query:.*?(?=\n\n)', '', final_report, flags=re.DOTALL)
    
    # Remove entire Research Framework sections (from start to first actual content section)
    if "Research Framework:" in final_report or "# Research Framework:" in final_report:

        framework_matches = re.search(r'(?:^|\n)(?:#\s*)?Research Framework:.*?(?=\n#|\n\*\*|\Z)', final_report, re.DOTALL)
        if framework_matches:
            framework_section = framework_matches.group(0)
            final_report = final_report.replace(framework_section, '')
    
    # Remove "Based on our discussion" title if it exists
    final_report = re.sub(r'^(?:#\s*)?Based on our discussion,.*?\n', '', final_report, flags=re.MULTILINE)
    
    # Also try to catch Objective sections and other framework components
    final_report = re.sub(r'^Objective:.*?\n\n', '', final_report, flags=re.MULTILINE | re.DOTALL)
    final_report = re.sub(r'^Key Aspects to Focus On:.*?\n\n', '', final_report, flags=re.MULTILINE | re.DOTALL)
    final_report = re.sub(r'^Constraints and Preferences:.*?\n\n', '', final_report, flags=re.MULTILINE | re.DOTALL)
    final_report = re.sub(r'^Areas to Explore in Depth:.*?\n\n', '', final_report, flags=re.MULTILINE | re.DOTALL)
    final_report = re.sub(r'^Preferred Sources, Perspectives, or Approaches:.*?\n\n', '', final_report, flags=re.MULTILINE | re.DOTALL)
    final_report = re.sub(r'^Scope, Boundaries, and Context:.*?\n\n', '', final_report, flags=re.MULTILINE | re.DOTALL)
    
    # Also remove any remaining individual problem framework lines
    final_report = re.sub(r'^Research Framework:.*?\n', '', final_report, flags=re.MULTILINE)
    final_report = re.sub(r'^Key Findings:.*?\n', '', final_report, flags=re.MULTILINE)
    final_report = re.sub(r'^Key aspects to focus on:.*?\n', '', final_report, flags=re.MULTILINE)

    report_title = await generate_title(llm, state['query'])
    
    # Remove the query or any long text description from the beginning of the report if present
    # This pattern removes lines that look like full query pasted as title or at the beginning
    if final_report.strip().startswith('# '):
        lines = final_report.split('\n')
        
        # Remove any extremely long title lines (likely a full query pasted as title)
        if len(lines) > 0 and len(lines[0]) > 80 and lines[0].startswith('# '):
            lines = lines[1:]  # Remove the first line
            final_report = '\n'.join(lines)
        
        # Also look for any text block before the actual title that might be the original query
        # or refined query description
        start_idx = 0
        title_idx = -1
        
        for i, line in enumerate(lines):
            if line.startswith('# ') and i > 0 and len(line) < 100:
                # Found what appears to be the actual title
                title_idx = i
                break
        
        # If we found a title after some text, remove everything before it
        if title_idx > 0:
            lines = lines[title_idx:]
            final_report = '\n'.join(lines)

    title_match = re.match(r'^#\s+.*?\n', final_report)
    if title_match:
        # Replace existing title with our generated one
        final_report = re.sub(r'^#\s+.*?\n', f'# {report_title}\n', final_report, count=1)
    else:

        final_report = f'# {report_title}\n\n{final_report}'
        
    # Also check for second line being the full query, which happens sometimes
    lines = final_report.split('\n')
    if len(lines) > 2 and len(lines[1]) > 80 and "query" not in lines[1].lower():
        lines.pop(1)  # Remove the second line if it looks like a query
        final_report = '\n'.join(lines)

    if "References" in final_report:

        references_match = re.search(r'#+\s*References.*?(?=#+\s+|\Z)', final_report, re.DOTALL)
        if references_match:
            references_section = references_match.group(0)
            
            # Always replace the references section with our properly formatted web citations
            console.print("[yellow]Ensuring references are properly formatted as web citations...[/]")

            citation_registry = state.get("citation_registry")
            citation_manager = state.get("citation_manager")
            formatted_citations = ""
            
            if citation_manager and citation_registry:

                citation_stats = citation_manager.get_learning_statistics()
                console.print(f"[bold green]Report references {len(citation_registry.citations)} sources with {citation_stats.get('total_learnings', 0)} tracked learnings[/]")

                validation_result = citation_registry.validate_citations(final_report)
                
                if not validation_result["valid"]:

                    out_of_range_count = len(validation_result.get("out_of_range_citations", set()))
                    other_invalid_count = len(validation_result["invalid_citations"]) - out_of_range_count
                    max_valid_id = validation_result.get("max_valid_id", 0)
                    
                    console.print(f"[bold yellow]Found {len(validation_result['invalid_citations'])} invalid citations in the report[/]")
                    
                    if out_of_range_count > 0:
                        console.print(f"[bold red]Found {out_of_range_count} out-of-range citations (exceeding max valid ID: {max_valid_id})[/]")
                    
                    # Remove invalid citations from the report
                    for invalid_cid in validation_result["invalid_citations"]:
                        # For out-of-range citations, replace with valid range indicator
                        if invalid_cid in validation_result.get("out_of_range_citations", set()):
                            replacement = f'[1-{max_valid_id}]'  # Suggest valid range
                            final_report = re.sub(f'\\[{invalid_cid}\\]', replacement, final_report)
                        else:
                            # Replace other invalid patterns like [invalid_cid] with [?]
                            final_report = re.sub(f'\\[{invalid_cid}\\]', '[?]', final_report)

                used_citations = validation_result["used_citations"]
                
                # If we have a citation manager, use its enhanced formatting
                if citation_manager and used_citations:

                    processed_text, bibliography_entries = citation_manager.get_citations_for_report(final_report)
                    
                    # Use the citation manager's bibliography formatter with APA style
                    if bibliography_entries:
                        formatted_citations = citation_manager.format_bibliography(bibliography_entries, "apa")
                        console.print(f"[bold green]Generated enhanced bibliography with {len(bibliography_entries)} entries[/]")
                # Fall back to regular citation formatting
                elif used_citations:

                    formatted_citations = await format_citations(
                        llm, 
                        state.get('selected_sources', []), 
                        state["sources"],
                        citation_registry
                    )
            
            # Replace references section with properly formatted ones
            if formatted_citations:
                new_references = f"# References\n\n{formatted_citations}\n"
                final_report = final_report.replace(references_section, new_references)
            elif state.get("formatted_citations"):
                new_references = f"# References\n\n{state['formatted_citations']}\n"
                final_report = final_report.replace(references_section, new_references)
            else:

                basic_references = []
                for i, url in enumerate(state.get("selected_sources", []), 1):
                    source_meta = next((s for s in state["sources"] if s.get("url") == url), {})
                    title = source_meta.get("title", "Untitled")
                    domain = url.split("//")[1].split("/")[0] if "//" in url else "Unknown Source"
                    date = source_meta.get("date", "n.d.")
                    
                    # Simpler citation format without the date
                    citation = f"[{i}] *{domain}*, \"{title}\", {url}"
                    basic_references.append(citation)
                
                new_references = f"# References\n\n" + "\n".join(basic_references) + "\n"
                final_report = final_report.replace(references_section, new_references)

    elapsed_time = time.time() - state["start_time"]
    minutes, seconds = divmod(int(elapsed_time), 60)

    state["messages"].append(AIMessage(content="Research complete. Generating final report..."))
    state["findings"] = final_report
    state["status"] = "Complete"

    if "citation_manager" in state:
        citation_stats = state["citation_manager"].get_learning_statistics()
        log_chain_of_thought(
            state, 
            f"Generated final report after {minutes}m {seconds}s with {citation_stats.get('total_sources', 0)} sources and {citation_stats.get('total_learnings', 0)} tracked learnings"
        )
    else:
        log_chain_of_thought(state, f"Generated final report after {minutes}m {seconds}s")
    
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state