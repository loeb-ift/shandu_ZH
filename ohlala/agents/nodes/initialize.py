"""
研究圖形的初始化節點。
"""
import os
import time
from rich.console import Console
from rich.panel import Panel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState
from ..utils.agent_utils import log_chain_of_thought, _call_progress_callback
from ...config import get_current_date
from ...prompts import SYSTEM_PROMPTS, USER_PROMPTS

console = Console()

class ResearchPlan(BaseModel):
    """研究計劃的結構化輸出。"""
    objectives: list[str] = Field(
        description="研究的明確目標",
        min_items=1
    )
    key_areas: list[str] = Field(
        description="需要研究的關鍵領域",
        min_items=1
    )
    methodology: str = Field(
        description="進行研究的方法",
    )
    expected_outcomes: list[str] = Field(
        description="研究的預期結果",
        min_items=1
    )

async def initialize_node(llm, date, progress_callback, state: AgentState) -> AgentState:
    """使用結構化輸出，初始化研究過程並制定研究計劃。"""
    console.print(Panel(f"[bold blue]開始研究：[/] {state['query']}", title="研究過程", border_style="blue"))
    state["start_time"] = time.time()
    state["status"] = "正在初始化研究"
    state["current_date"] = date or get_current_date()
    
    try:
        # 使用完全直接的方法以避免模板問題
        direct_prompt = f"""你是一位專業的研究代理，負責制定一份全面的研究計劃。當前日期：{state['current_date']}

請為以下查詢制定一份詳細的研究計劃：{state['query']}

你的計劃必須包含以下清晰標識的部分：

## 目標
- 列出3 - 5個清晰的研究目標。

## 關鍵研究領域
- 列出4 - 6個需要研究的特定領域或方面。

## 方法論
- 描述進行這項研究的方法。
- 包括信息來源和分析方法。

## 預期結果
- 列出3 - 5個這項研究的預期結果或交付物。

使用清晰的部分標題和項目符號格式化你的回覆，以便清晰易懂。在規劃中要具體詳細。
"""
        # 將直接提示發送給模型
        response = await llm.ainvoke(direct_prompt)

        research_text = response.content

        import re
        objectives = []
        key_areas = []
        methodology = ""
        expected_outcomes = []

        objectives_section = re.search(r'(?:objectives|goals|aims)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', research_text.lower(), re.IGNORECASE | re.DOTALL)
        if objectives_section:
            objectives_text = objectives_section.group(1).strip()
            objectives = [line.strip().strip('-*').strip() for line in objectives_text.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        areas_section = re.search(r'(?:key areas|areas to investigate|investigation areas)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', research_text.lower(), re.IGNORECASE | re.DOTALL)
        if areas_section:
            areas_text = areas_section.group(1).strip()
            key_areas = [line.strip().strip('-*').strip() for line in areas_text.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        methodology_section = re.search(r'(?:methodology|approach|method)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', research_text.lower(), re.IGNORECASE | re.DOTALL)
        if methodology_section:
            methodology = methodology_section.group(1).strip()
        
        outcomes_section = re.search(r'(?:expected outcomes|outcomes|results|expected results)(?:\s*:|\s*\n)([^#]*?)(?:#|$)', research_text.lower(), re.IGNORECASE | re.DOTALL)
        if outcomes_section:
            outcomes_text = outcomes_section.group(1).strip()
            expected_outcomes = [line.strip().strip('-*').strip() for line in outcomes_text.split('\n') if line.strip() and not line.strip().startswith('#')]

        if not objectives:
            objectives = ["理解 {state['query']} 的關鍵方面"]
        if not key_areas:
            key_areas = ["主要概念和定義", "當前應用和示例", "未來趨勢和發展"]
        if not methodology:
            methodology = "對可用文獻進行系統性回顧，並分析當前應用和示例。"
        if not expected_outcomes:
            expected_outcomes = ["全面理解 {state['query']}", "識別關鍵挑戰和機遇"]

        formatted_plan = "# 研究計劃\n\n"
        
        formatted_plan += "## 目標\n\n"
        for objective in objectives:
            formatted_plan += f"- {objective}\n"
        
        formatted_plan += "\n## 關鍵研究領域\n\n"
        for area in key_areas:
            formatted_plan += f"- {area}\n"
        
        formatted_plan += f"\n## 方法論\n\n{methodology}\n"
        
        formatted_plan += "\n## 預期結果\n\n"
        for outcome in expected_outcomes:
            formatted_plan += f"- {outcome}\n"
        
        state["messages"].append(HumanMessage(content=f"規劃對 {state['query']} 的研究..."))
        state["messages"].append(AIMessage(content=formatted_plan))
        state["findings"] = f"{formatted_plan}\n\n# 初始研究結果\n\n"
        
    except Exception as e:
        from ....utils.logger import log_error
        log_error("結構化計劃生成中出錯", e, 
                 context=f"查詢：{state['query']}，函數：initialize_node")
        console.print(f"[dim red]結構化計劃生成中出錯：{str(e)}。使用更簡單的方法...[/dim red]")
        try:
            # 更簡單的備用方法
            response = await llm.ainvoke(f"""為 {state['query']} 制定一份研究計劃。

包括：
1. 主要目標
2. 關鍵研究領域
3. 方法/方法論
4. 預期結果

保持簡潔實用。
""")
            
            cleaned_plan = response.content.replace("**", "").replace("# ", "").replace("## ", "")
            
            state["messages"].append(HumanMessage(content=f"規劃對 {state['query']} 的研究..."))
            state["messages"].append(AIMessage(content=cleaned_plan))
            state["findings"] = f"# 研究計劃\n\n{cleaned_plan}\n\n# 初始研究結果\n\n"
        except Exception as e2:
            console.print(f"[dim red]備用計劃生成中出錯：{str(e2)}。使用最小化計劃...[/dim red]")
            
            minimal_plan = f"針對 {state['query']} 的研究計劃\n\n- 研究關鍵方面\n- 分析相關來源\n- 綜合研究結果"
            
            state["messages"].append(HumanMessage(content=f"規劃對 {state['query']} 的研究..."))
            state["messages"].append(AIMessage(content=minimal_plan))
            state["findings"] = f"# 研究計劃\n\n{minimal_plan}\n\n# 初始研究結果\n\n"
    
    log_chain_of_thought(state, f"為查詢 {state['query']} 創建了研究計劃")
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state
