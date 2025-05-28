"""
來源選擇節點。
"""
import os
import re
from rich.console import Console
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState
from ..utils.agent_utils import log_chain_of_thought, _call_progress_callback
from ...prompts import SYSTEM_PROMPTS, USER_PROMPTS

console = Console()

# 來源選擇的結構化輸出模型
class SourceSelection(BaseModel):
    """來源選擇的結構化輸出。"""
    selected_sources: list[str] = Field(
        description="要包含在報告中的最有價值來源的URL列表",
        min_items=1
    )
    selection_rationale: str = Field(
        description="解釋為什麼選擇這些來源"
    )

async def smart_source_selection(llm, progress_callback, state: AgentState) -> AgentState:
    """使用結構化輸出選擇報告的相關來源。"""
    state["status"] = "選擇最有價值的來源"
    console.print("[bold blue]選擇最相關和高質量的來源...[/]")

    all_source_urls = []
    for analysis in state["content_analysis"]:
        if "sources" in analysis and isinstance(analysis["sources"], list):
            for url in analysis["sources"]:
                if url not in all_source_urls:
                    all_source_urls.append(url)
    
    # 如果來源太多，使用智能選擇進行過濾
    if len(all_source_urls) > 25:

        sources_text = ""
        for i, url in enumerate(all_source_urls, 1):

            source_meta = {}
            for source in state["sources"]:
                if source.get("url") == url:
                    source_meta = source
                    break

            sources_text += f"來源 {i}:\nURL: {url}\n"
            if source_meta.get("title"):
                sources_text += f"標題: {source_meta.get('title')}\n"
            if source_meta.get("snippet"):
                sources_text += f"摘要: {source_meta.get('snippet')}\n"
            if source_meta.get("date"):
                sources_text += f"日期: {source_meta.get('date')}\n"
            sources_text += "\n"
        
        try:
            # 使用完全直接的方法以避免模板問題
            direct_prompt = f"""你必須仔細選擇本研究報告中最有價值的來源。 

研究主題：{state['query']}

要評估的來源：
{sources_text}

選擇標準：
1. 直接相關性：來源必須明確涉及研究問題的核心方面
2. 信息質量：來源應提供重要的獨特數據或見解
3. 可信度：來源應具有權威性和可靠性
4. 時效性：來源應足夠新穎，適用於該主題
5. 多樣性：來源應涵蓋不同的觀點或方面

指示：
- 從列表中選擇15 - 20個最有價值的來源
- 僅返回你選擇的來源的確切URL
- 按重要性順序列出URL（最有價值的在前）
- 每行一個URL，無解釋或編號
"""
            # 直接將提示發送給模型
            response = await llm.ainvoke(direct_prompt)

            response_text = response.content

            selected_urls = []
            lines = response_text.split('\n')
            
            # 遍歷每行，查找URL
            for line in lines:

                for url in all_source_urls:
                    if url in line:
                        if url not in selected_urls:
                            selected_urls.append(url)
                            break

            rationale = "根據相關性、可信度和關鍵方面的覆蓋範圍選擇來源。"
            rationale_section = re.search(r'(?:rationale|reasoning|explanation|justification)(?:\s*:|\s*\n)([^#]*?)(?:$|#)', response_text.lower(), re.IGNORECASE | re.DOTALL)
            if rationale_section:
                rationale = rationale_section.group(1).strip()
            
            # 記錄選擇理由
            log_chain_of_thought(state, f"來源選擇理由：{rationale}")
            
        except Exception as e:
            console.print(f"[dim red]結構化來源選擇中出錯：{str(e)}。使用更簡單的方法...[/dim red]")
            from ...utils.logger import log_error
            log_error("結構化來源選擇中出錯", e, 
                 context=f"查詢：{state['query']}，函數：smart_source_selection")
            current_file = os.path.basename(__file__)
            #with open('example.txt', 'a') as file:
                # 追加當前文件的名稱和一些文本
                #file.write(f'This line was written by: {current_file}\n')
                #file.write(f'Error {e}.\n')

            # 回退到非結構化方法
            try:
                # 更簡單的回退方法
                response = await llm.ainvoke(f"""為 {state['query']} 選擇15個最佳來源

從這些來源中選擇：
{sources_text}

僅返回URL，每行一個。
""")

                selected_urls = []
                for url in all_source_urls:
                    if url in response.content:
                        selected_urls.append(url)
            except Exception as e2:
                console.print(f"[dim red]回退來源選擇中出錯：{str(e2)}。使用預設選擇...[/dim red]")
                selected_urls = []
        
        # 確保至少有一些來源
        if not selected_urls and all_source_urls:
            # 如果選擇失敗，取前15 - 20個來源
            selected_urls = all_source_urls[:min(20, len(all_source_urls))]
            
        state["selected_sources"] = selected_urls
        log_chain_of_thought(state, f"從 {len(all_source_urls)} 個總來源中選擇了 {len(selected_urls)} 個最相關的來源")
    else:
        # 如果來源不多，使用所有來源
        state["selected_sources"] = all_source_urls
        log_chain_of_thought(state, f"使用所有 {len(all_source_urls)} 個來源作為最終報告")
    
    if progress_callback:
        await _call_progress_callback(progress_callback, state)
    return state
