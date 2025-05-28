"""
研究圖形的查詢生成節點。
"""
import os
import re
from rich.console import Console
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState
from ..utils.agent_utils import log_chain_of_thought, _call_progress_callback
from ...prompts import SYSTEM_PROMPTS, USER_PROMPTS

console = Console()

# 查詢生成的結構化輸出模型
class SearchQueries(BaseModel):
    """搜尋查詢生成的結構化輸出。"""
    queries: list[str] = Field(
        description="用於進一步研究主題的搜尋查詢列表",
        min_items=1
    )
    rationale: str = Field(
        description="解釋為什麼選擇這些查詢以及它們如何幫助研究"
    )

async def generate_queries_node(llm, progress_callback, state: AgentState) -> AgentState:
    """使用結構化輸出，根據當前研究結果生成有針對性的搜尋查詢。"""
    state["status"] = "正在生成研究查詢"
    console.print("[bold yellow]正在生成有針對性的搜尋查詢...[/]")
    
    try:
        # 使用完全直接的方法以避免模板問題
        direct_prompt = f"""生成 {state['breadth']} 個特定的搜尋查詢，以研究以下主題：

主要查詢：{state['query']}

要求：
1. 精確生成 {state['breadth']} 個搜尋查詢。
2. 查詢應該自然且口語化（就像有人在Google中輸入的那樣）。
3. 每個查詢應該針對特定的事實、數據點或觀點。
4. 保持查詢直接且簡潔 - 避免複雜的學術用語。

今日日期：{state['current_date']}

當前研究結果：
{state['findings'][:2000]}

僅返回搜尋查詢本身，每行一個，不包含任何額外的文字、編號或解釋。
"""
        # 直接將提示發送給模型
        response = await llm.ainvoke(direct_prompt)

        new_queries = [line.strip() for line in response.content.split("\n") if line.strip()]
        # 移除任何編號、項目符號或其他格式
        new_queries = [re.sub(r'^[\d\s\-\*•\.\)]+\s*', '', line).strip() for line in new_queries]
        # 移除諸如 "Here are..."、"I'll search for..." 等短語
        new_queries = [re.sub(r'^(here are|i will|i\'ll|let me|these are|i recommend|completed:|search for:).*?:', '', line, flags=re.IGNORECASE).strip() for line in new_queries]
        # 過濾掉任何空行或看起來不像實際查詢的行
        new_queries = [q for q in new_queries if q and len(q.split()) >= 2 and not q.lower().startswith(("query", "search", "investigate", "explore", "research"))]
        # 限制為指定的寬度
        new_queries = new_queries[:state["breadth"]]
        
        log_chain_of_thought(state, f"生成了 {len(new_queries)} 個用於研究的搜尋查詢")
        
    except Exception as e:
        from ....utils.logger import log_error
        log_error("結構化查詢生成中出錯", e, 
                 context=f"查詢：{state['query']}，函數：generate_queries_node")
        console.print(f"[dim red]結構化查詢生成中出錯：{str(e)}。使用更簡單的方法...[/dim red]")
        try:
            # 更簡單的備用方法
            response = await llm.ainvoke(f"為 {state['query']} 生成 {state['breadth']} 個簡單的搜尋查詢。每行僅返回一個查詢。")

            new_queries = [line.strip() for line in response.content.split("\n") if line.strip()]
            # 移除任何編號、項目符號或其他格式
            new_queries = [re.sub(r'^[\d\s\-\*•\.\)]+\s*', '', line).strip() for line in new_queries]
            # 移除諸如 "Here are..."、"I'll search for..." 等短語
            new_queries = [re.sub(r'^(here are|i will|i\'ll|let me|these are|i recommend|completed:|search for:).*?:', '', line, flags=re.IGNORECASE).strip() for line in new_queries]
            # 過濾掉任何空行或看起來不像實際查詢的行
            new_queries = [q for q in new_queries if q and len(q.split()) >= 2 and not q.lower().startswith(("query", "search", "investigate", "explore", "research"))]
            # 限制為指定的寬度
            new_queries = new_queries[:state["breadth"]]
        except Exception as e2:
            console.print(f"[dim red]備用查詢生成中出錯：{str(e2)}。使用預設查詢...[/dim red]")

            new_queries = [
                f"{state['query']} 最新研究",
                f"{state['query']} 示例",
                f"{state['query']} 應用"
            ][:state["breadth"]]
    
    if not new_queries and state["query"]:
        new_queries = [state["query"]]
    
    state["messages"].append(HumanMessage(content="正在生成新的研究方向..."))
    state["messages"].append(AIMessage(content="生成的查詢：\n" + "\n".join(new_queries)))
    state["subqueries"].extend(new_queries)
    
    console.print("[bold green]生成的搜尋查詢：[/]")
    for i, query in enumerate(new_queries, 1):
        console.print(f"  {i}. {query}")
    
    log_chain_of_thought(state, f"生成了 {len(new_queries)} 個用於研究的搜尋查詢")
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state
