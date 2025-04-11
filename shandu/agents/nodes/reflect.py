"""
研究圖形的反思節點。
"""
import os
from rich.console import Console
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState
from ..utils.agent_utils import log_chain_of_thought, _call_progress_callback
from ...prompts import SYSTEM_PROMPTS, USER_PROMPTS, safe_format

console = Console()

# 反思的結構化輸出模型
class ResearchReflection(BaseModel):
    """研究反思的結構化輸出。"""
    key_insights: list[str] = Field(
        description="到目前為止從研究中獲得的關鍵見解",
        min_items=1
    )
    knowledge_gaps: list[str] = Field(
        description="當前研究中已識別的知識差距",
        min_items=1
    )
    next_steps: list[str] = Field(
        description="研究的建議下一步驟",
        min_items=1
    )
    reflection_summary: str = Field(
        description="對當前研究狀態的整體反思"
    )

async def reflect_node(llm, progress_callback, state: AgentState) -> AgentState:
    """使用結構化輸出，反思當前研究結果，以識別差距和機遇。"""
    state["status"] = "正在反思研究結果"
    console.print("[bold yellow]正在反思當前研究結果...[/]")
    
    try:
        # 使用safe_format而不是手動轉義
        current_date = state['current_date']
        findings = state['findings'][:3000]
        
        direct_prompt = safe_format("""分析以下研究結果並提供詳細的反思。今日日期：{current_date}

研究結果：
{findings}

你的反思必須包含以下清晰標識的部分：

## 關鍵見解
- 列出研究中最重要的發現和見解。
- 評估每個見解的證據強度。

## 知識差距
- 識別仍然未解決的具體問題。
- 解釋為什麼這些差距很重要。

## 下一步驟
- 建議需要深入研究的具體領域。
- 推薦解決知識差距的研究方法。

## 整體反思
- 對研究進展進行全面評估。
- 評估研究結果的整體質量和可靠性。

使用清晰的部分標題和項目符號格式化你的回覆，以便清晰易懂。""", current_date=current_date, findings=findings)
        # 直接將提示發送給模型
        response = await llm.ainvoke(direct_prompt)

        reflection_text = response.content

        import re
        key_insights = []
        knowledge_gaps = []
        next_steps = []
        reflection_summary = ""

        insights_section = re.search(r'(?:key insights|insights|key findings)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', reflection_text.lower(), re.IGNORECASE | re.DOTALL)
        if insights_section:
            insights_text = insights_section.group(1).strip()
            key_insights = [line.strip().strip('-*').strip() for line in insights_text.split('\n') if line.strip() and not line.strip().startswith('#')]

        gaps_section = re.search(r'(?:knowledge gaps|gaps|questions|unanswered questions)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', reflection_text.lower(), re.IGNORECASE | re.DOTALL)
        if gaps_section:
            gaps_text = gaps_section.group(1).strip()
            knowledge_gaps = [line.strip().strip('-*').strip() for line in gaps_text.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        steps_section = re.search(r'(?:next steps|steps|recommendations|future directions)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', reflection_text.lower(), re.IGNORECASE | re.DOTALL)
        if steps_section:
            steps_text = steps_section.group(1).strip()
            next_steps = [line.strip().strip('-*').strip() for line in steps_text.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        summary_section = re.search(r'(?:overall reflection|reflection summary|summary|conclusion)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', reflection_text.lower(), re.IGNORECASE | re.DOTALL)
        if summary_section:
            reflection_summary = summary_section.group(1).strip()
        
        if not key_insights:
            key_insights = ["關於 {state['query']} 的研究正在進行中"]
        if not knowledge_gaps:
            knowledge_gaps = ["需要更多特定方面的詳細信息"]
        if not next_steps:
            next_steps = ["繼續研究主要方面", "尋找更多具體示例"]
        if not reflection_summary:
            reflection_summary = "研究正在取得進展，並已發現有價值的信息，但在關鍵領域還需要進一步研究。"

        formatted_reflection = "## 關鍵見解\n\n"
        for insight in key_insights:
            formatted_reflection += f"- {insight}\n"
        
        formatted_reflection += "\n## 知識差距\n\n"
        for gap in knowledge_gaps:
            formatted_reflection += f"- {gap}\n"
        
        formatted_reflection += "\n## 下一步驟\n\n"
        for step in next_steps:
            formatted_reflection += f"- {step}\n"
        
        formatted_reflection += f"\n## 整體反思\n\n{reflection_summary}\n"
        
        state["messages"].append(HumanMessage(content="分析當前研究結果..."))
        state["messages"].append(AIMessage(content=formatted_reflection))
        state["findings"] += f"\n\n## 對當前研究結果的反思\n\n{formatted_reflection}\n\n"
        
    except Exception as e:
        from ...utils.logger import log_error
        log_error("結構化反思中出錯", e, 
                 context=f"函數：reflect_node")
        console.print(f"[dim red]結構化反思中出錯：{str(e)}。使用更簡單的方法...[/dim red]")
        try:
            # 在備用情況下也使用safe_format
            fallback_findings = state['findings'][:2000]
            
            fallback_prompt = safe_format("""反思這些研究結果：

{findings}

包括： 
1. 關鍵見解
2. 知識差距
3. 下一步驟
4. 整體評估
""", findings=fallback_findings)
            
            response = await llm.ainvoke(fallback_prompt)
            
            reflection_content = response.content
            
            state["messages"].append(HumanMessage(content="分析當前研究結果..."))
            state["messages"].append(AIMessage(content=reflection_content))
            state["findings"] += f"\n\n## 對當前研究結果的反思\n\n{reflection_content}\n\n"
        except Exception as e2:
            console.print(f"[dim red]備用反思中出錯：{str(e2)}。使用最小化反思...[/dim red]")
            
            minimal_reflection = "## 研究反思\n\n研究正在進行中。需要進一步研究以更全面地理解該主題。"
            
            state["messages"].append(HumanMessage(content="分析當前研究結果..."))
            state["messages"].append(AIMessage(content=minimal_reflection))
            state["findings"] += f"\n\n## 對當前研究結果的反思\n\n{minimal_reflection}\n\n"
    
    log_chain_of_thought(state, "完成對當前研究結果的反思")
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state
