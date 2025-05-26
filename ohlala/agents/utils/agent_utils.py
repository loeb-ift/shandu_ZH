"""Agent utility functions."""
from typing import List, Dict, Optional, Any, Callable, Union, TypedDict, Sequence
from dataclasses import dataclass
import time
import re
import asyncio
import signal
import threading
import sys
import os
from datetime import datetime
from rich.console import Console
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markup import escape
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState

console = Console()

# Global shutdown flag for graceful termination
_shutdown_requested = False
_shutdown_lock = threading.Lock()
_shutdown_counter = 0
_MAX_SHUTDOWN_ATTEMPTS = 3

def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(sig, frame):
        global _shutdown_requested, _shutdown_counter
        with _shutdown_lock:
            _shutdown_requested = True
            _shutdown_counter += 1
            
            if _shutdown_counter == 1:
                console.print("\n[yellow]Shutdown requested. Completing current operations...[/]")
            elif _shutdown_counter == 2:
                console.print("\n[orange]Second shutdown request. Canceling operations...[/]")
            elif _shutdown_counter >= _MAX_SHUTDOWN_ATTEMPTS:
                console.print("\n[bold red]Forced exit requested. Exiting immediately.[/]")
                # Force exit after multiple attempts
                os._exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# Call this at application startup
setup_signal_handlers()

def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested."""
    with _shutdown_lock:
        return _shutdown_requested

def get_shutdown_level() -> int:
    """Get the current shutdown level (number of attempts)."""
    with _shutdown_lock:
        return _shutdown_counter

def get_user_input(prompt: str) -> str:
    """Get formatted user input with shutdown handling."""
    console.print(prompt, style="yellow")

    if is_shutdown_requested():
        console.print("[yellow]Shutdown requested, skipping user input...[/]")
        return "any"  # Return a generic answer to allow the process to continue to shutdown
    
    try:
        return input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        with _shutdown_lock:
            global _shutdown_requested
            _shutdown_requested = True
        console.print("\n[yellow]Input interrupted. Proceeding with shutdown...[/]")
        return "any"  # Return a generic answer to allow the process to continue to shutdown
    except UnicodeDecodeError as e:
        console.print(f"[dim red]Encoding error: {str(e)}. Using default answer.[/dim red]")
        return "any"  # Fallback to a generic answer

def should_continue(state: AgentState) -> str:
    """Check if research should continue."""
    # First check if shutdown was requested
    if is_shutdown_requested():
        # If this is a forceful shutdown (second attempt or higher)
        if get_shutdown_level() >= 2:
            console.print("[bold red]Forceful shutdown requested. Ending research immediately.[/]")
            return "end"
        
        # For first shutdown request, try to complete gracefully
        console.print("[yellow]Shutdown requested. Completing current depth before ending.[/]")
        
        # If we're already at the end of a depth cycle, end now
        if state.get("current_depth", 0) >= state.get("depth", 1):
            return "end"
        
        # Otherwise, allow the current depth to complete
        return "continue"

    if "iteration_count" not in state:
        state["iteration_count"] = 1
    else:
        state["iteration_count"] += 1

    # This is separate from depth/breadth and ensures we won't get stuck
    if state["iteration_count"] >= 25:
        console.print("[yellow]Maximum iterations reached. Ending research to prevent infinite loop.[/]")
        return "end"
    
    # Then check if we've reached the desired depth
    if state["current_depth"] < state["depth"]:
        return "continue"
    
    return "end"

def log_chain_of_thought(state: AgentState, thought: str) -> None:
    """
    Log a thought to the agent's chain of thought with timestamp.
    
    Args:
        state: The current agent state
        thought: The thought to log
    """
    # Sanitize the thought to prevent Rich markup issues
    sanitized_thought = thought
    # Remove any square brackets that could be misinterpreted as markup
    sanitized_thought = re.sub(r'\[[^\]]*\]', '', sanitized_thought)
    # Remove any orphaned brackets or tags
    sanitized_thought = re.sub(r'\[\/?[^\]]*\]?', '', sanitized_thought)
    sanitized_thought = re.sub(r'\[\]', '', sanitized_thought)
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    state["chain_of_thought"].append(f"[{timestamp}] {sanitized_thought}")

def display_research_progress(state: AgentState) -> Tree:
    """
    Create a rich tree display of current research progress.
    
    Args:
        state: The current agent state
        
    Returns:
        Rich Tree object for display
    """
    elapsed_time = time.time() - state["start_time"]
    minutes, seconds = divmod(int(elapsed_time), 60)
    
    # Sanitize status to prevent markup errors
    status_raw = state["status"]
    status = re.sub(r'\[[^\]]*\]', '', status_raw)  # Remove any potential markup
    status = escape(status)  # Escape any remaining characters
    
    phase = "Research" if "depth" in status.lower() or any(word in status.lower() for word in ["searching", "querying", "reflecting", "analyzing"]) else "Report Generation"
    
    tree = Tree(f"[bold blue]{phase} Progress: {status}")

    stats_node = tree.add(f"[cyan]Stats")
    stats_node.add(f"[blue]Time Elapsed:[/] {minutes}m {seconds}s")
    
    if phase == "Research":
        # Display research-specific stats
        stats_node.add(f"[blue]Current Depth:[/] {state['current_depth']}/{state['depth']}")
        stats_node.add(f"[blue]Sources Found:[/] {len(state['sources'])}")
        stats_node.add(f"[blue]Subqueries Explored:[/] {len(state['subqueries'])}")
        
        # Show current research paths - with safety checks
        if state["subqueries"]:
            queries_node = tree.add("[green]Current Research Paths")
            # Safely get the last N queries based on breadth
            breadth = max(1, state.get("breadth", 1))  # Ensure breadth is at least 1
            
            # Limit to actual number of queries available
            display_count = min(breadth, len(state["subqueries"]))
            
            if display_count > 0:
                for i in range(-display_count, 0):  # Get the last 'display_count' elements
                    if i + len(state["subqueries"]) >= 0:  # Safety check
                        query_text = state["subqueries"][i]
                        # Sanitize the query text
                        query_text = re.sub(r'\[[^\]]*\]', '', query_text)
                        query_text = escape(query_text)
                        queries_node.add(query_text)
    else:
        # Display report generation specific stats
        stats_node.add(f"[blue]Sources Selected:[/] {len(state.get('selected_sources', []))}")
        
        # Show report generation progress
        report_progress = tree.add("[green]Report Generation Progress")
        if state.get("selected_sources"):
            report_progress.add("[green]✓[/green] Sources selected")
        if state.get("formatted_citations"):
            report_progress.add("[green]✓[/green] Citations formatted")
        if state.get("initial_report"):
            report_progress.add("[green]✓[/green] Initial report generated")
        if state.get("enhanced_report"):
            report_progress.add("[green]✓[/green] Report enhanced with details")
        if state.get("final_report"):
            report_progress.add("[green]✓[/green] Key sections expanded")
    
    # Show recent thoughts regardless of phase
    if state["chain_of_thought"]:
        thoughts_node = tree.add("[yellow]Recent Thoughts")
        for thought in state["chain_of_thought"][-3:]:
            thoughts_node.add(thought)
    
    # Show latest findings only in research phase
    if phase == "Research" and state["findings"]:
        findings_node = tree.add("[magenta]Latest Findings")
        sections = state["findings"].split("\n\n")
        for section in sections[-2:]:
            if section.strip():
                # Sanitize findings text to prevent markup errors
                section_text = section.strip()[:100] + "..." if len(section.strip()) > 100 else section.strip()
                # Remove any square brackets that could be misinterpreted as markup
                section_text = re.sub(r'\[[^\]]*\]', '', section_text)
                # Remove any orphaned brackets or tags
                section_text = re.sub(r'\[\/?[^\]]*\]?', '', section_text)
                section_text = re.sub(r'\[\]', '', section_text)
                # Escape any remaining characters that could be misinterpreted
                section_text = escape(section_text)
                findings_node.add(section_text)
    
    # Show shutdown status if requested
    if is_shutdown_requested():
        tree.add(f"[bold red]Shutdown requested. Attempt {get_shutdown_level()}/{_MAX_SHUTDOWN_ATTEMPTS}")
    
    return tree

async def _call_progress_callback(callback: Optional[Callable], state: AgentState) -> None:
    """
    Call the progress callback with the current state if provided.
    
    Args:
        callback: The callback function
        state: The current agent state
    """
    # Sanitize state values that will be displayed to prevent Rich markup errors
    if "status" in state:
        state["status"] = escape(re.sub(r'\[[^\]]*\]', '', state["status"]))
    
    if callback:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(state)
            else:
                callback(state)
        except Exception as e:
            # Sanitize the error message before displaying
            error_msg = str(e)
            error_msg = re.sub(r'\[[^\]]*\]', '', error_msg)
            error_msg = re.sub(r'\[\/?[^\]]*\]?', '', error_msg)
            error_msg = escape(error_msg)
            console.print(f"[dim red]Error in progress callback: {error_msg}[/dim red]")

# Structured output model for query clarification
class ClarificationQuestions(BaseModel):
    """Structured output for query clarification questions."""
    questions: list[str] = Field(
        description="List of clarifying questions to better understand the research needs",
        min_items=1,
        max_items=3
    )

class RefinedQuery(BaseModel):
    """Structured output for refined query."""
    query: str = Field(description="The refined, comprehensive research query")
    explanation: str = Field(description="Explanation of how the query was refined based on the Q&A")

async def clarify_query(query: str, llm, date: Optional[str] = None, system_prompt: str = "", user_prompt: str = "") -> str:
    """Interactive query clarification process with structured output."""
    from ...prompts import SYSTEM_PROMPTS, USER_PROMPTS
    
    current_date = date or datetime.now().strftime("%Y-%m-%d")
    console.print(f"[bold blue]Initial Query:[/] {query}")

    if not system_prompt:
        # Use direct string with current_date instead of format
        clarify_prompt = SYSTEM_PROMPTS.get("clarify_query", "")
        system_prompt = f"""You must generate clarifying questions to refine the research query with strict adherence to:
- Eliciting specific details about user goals, scope, and knowledge level.
- Avoiding extraneous or trivial queries.
- Providing precisely 4-5 targeted questions.

Today's date: {current_date}.

These questions must seek to clarify the exact focal points, the depth of detail, constraints, and user background knowledge. Provide them succinctly and plainly, with no added commentary."""
    
    if not user_prompt:
        user_prompt = USER_PROMPTS.get("clarify_query", "")
    
    try:
        # Use a simpler approach to avoid issues with prompt templates
        try:
            # Direct approach without structured output
            response = await llm.ainvoke(f"""
            {system_prompt}
            
            Generate 3-5 direct, specific questions to better understand the research needs for the query: "{query}"
            
            Focus on:
            1. Clarifying the specific areas the user wants to explore
            2. The level of detail needed
            3. Specific sources or perspectives to include
            4. Time frame or context relevant to the query
            
            IMPORTANT: Provide ONLY the questions themselves, without any introduction or preamble.
            Each question should be clear, direct, and standalone.
            """)

            questions = [q.strip() for q in response.content.split("\n") if q.strip() and "?" in q]
            
            # Limit to top 3-5 questions
            questions = questions[:5]
        except Exception as e:
            console.print(f"[dim red]Error in question generation: {str(e)}. Using default questions.[/dim red]")
            questions = []
    except Exception as e:
        from ....utils.logger import log_error
        log_error("Error in clarify_query", e, 
                 context=f"Query: {query}, Function: clarify_query")
        console.print(f"[dim red]Error in structured question generation: {str(e)}. Using simpler approach.[/dim red]")
        try:
            # Direct approach without structured output
            response = await llm.ainvoke(f"Generate 3 direct clarifying questions for the research query: {query}")

            questions = [q.strip() for q in response.content.split("\n") if q.strip() and "?" in q]
        except Exception as e2:
            console.print(f"[dim red]Error in fallback question generation: {str(e2)}. Using default questions.[/dim red]")
            questions = []
        
        # If we couldn't extract questions, create some generic ones
        if not questions:
            questions = [
                "What specific application or area of this topic are you most interested in?",
                "What is the intended audience or purpose of this research?",
                "Are you interested in current applications, future trends, ethical considerations, or a combination of these aspects?"
            ]
    
    # Limit to 3 questions
    questions = questions[:3]

    answers = []
    for q in questions:

        if is_shutdown_requested():
            console.print("[yellow]Shutdown requested, using generic answers...[/]")
            answers.append("any")  # Use a generic answer
            continue
            
        answer = get_user_input(q)
        answers.append(answer)
    
    qa_text = "\n".join([f"Q: {q}\nA: {a}" for q, a in zip(questions, answers)])

    refine_system_prompt = f"""You must refine the research query into a strict, focused direction based on user-provided answers. Today's date: {current_date}.

REQUIREMENTS:
- DO NOT present any "Research Framework" or "Objective" headings.
- Provide a concise topic statement followed by 2-3 paragraphs integrating all key points from the user.
- Preserve all critical details mentioned by the user.
- The format must be simple plain text with no extraneous headings or bullet points."""
    
    refine_user_prompt = USER_PROMPTS.get("refine_query", "")
    
    try:
        # Use direct approach without structured output
        response = await llm.ainvoke(f"""
        {refine_system_prompt}
        
        Original query: {query}
        Follow-up questions and answers:
        {qa_text}
        
        Based on this information, create a comprehensive, well-structured research query.
        The query should be clear, focused, and incorporate all relevant information from the answers.
        """)
        
        refined_context_raw = response.content

        refined_context = refined_context_raw.replace("**", "").replace("# ", "").replace("## ", "")
        refined_context = re.sub(r'^(?:Based on our discussion,|Following our conversation,|As per our discussion,).*?(?:refined topic:|research the following:|exploring|analyze):\s*', '', refined_context, flags=re.IGNORECASE)
        refined_context = re.sub(r'Based on our discussion.*?(?=\.)\.', '', refined_context, flags=re.IGNORECASE)
    except Exception as e:
        from ....utils.logger import log_error
        log_error("Error in clarify_query", e, 
                 context=f"Query: {query}, Function: clarify_query")
        console.print(f"[dim red]Error in structured query refinement: {str(e)}. Using simpler approach.[/dim red]")
        try:
            # Direct approach without structured output
            response = await llm.ainvoke(f"""
            Original query: {query}
            
            Follow-up questions and answers:
            {qa_text}
            
            Based on this information, create a comprehensive, well-structured research query.
            """)
            
            refined_context_raw = response.content

            return refined_context
        except Exception as e2:
            console.print(f"[dim red]Error in fallback query refinement: {str(e2)}. Using original query.[/dim red]")
            refined_context = query
    
    console.print(f"\n[bold green]Refined Research Query:[/]\n{refined_context}")
    return refined_context
