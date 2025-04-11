"""
研究圖形的搜尋節點。
"""
import asyncio
import time
import random
import logging
from typing import List, Dict, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from ..processors.content_processor import AgentState, is_relevant_url, process_scraped_item, analyze_content
from ..utils.agent_utils import log_chain_of_thought, _call_progress_callback, is_shutdown_requested
from ...search.search import SearchResult

console = Console()

# 搜尋結果的結構化輸出模型
class SearchResultAnalysis(BaseModel):
    """搜尋結果分析的結構化輸出。"""
    relevant_urls: list[str] = Field(
        description="與查詢相關的URL列表",
        min_items=0
    )
    analysis: str = Field(
        description="搜尋結果的分析"
    )

logger = logging.getLogger(__name__)

async def search_node(llm, searcher, scraper, progress_callback, state: AgentState) -> AgentState:
    """
    根據當前的子查詢搜尋信息。
    
    參數:
        llm: 要使用的語言模型
        searcher: 要使用的搜尋引擎
        scraper: 要使用的網頁抓取器
        progress_callback: 用於進度更新的回調函數
        state: 當前代理狀態
        
    返回:
        更新後的代理狀態
    """
    if is_shutdown_requested():
        state["status"] = "已請求關閉，跳過搜尋"
        log_chain_of_thought(state, "已請求關閉，跳過搜尋")
        return state
    
    state["status"] = f"正在搜尋信息（深度 {state['current_depth']}）"
    
    breadth = state["breadth"]
    if len(state["subqueries"]) > 0:
        recent_queries = state["subqueries"][-breadth:]
    else:
        recent_queries = [state["query"]]

    async def process_query(query, query_idx):
        if is_shutdown_requested():
            log_chain_of_thought(state, f"已請求關閉，在 {query_idx} 個查詢後停止搜尋")
            return
            
        logger.info(f"處理查詢 {query_idx+1}/{len(recent_queries)}: {query}")
        console.print(f"執行搜尋：{query}")
        state["status"] = f"正在搜尋：{query}"
        
        # 使用多個引擎搜尋查詢，以獲得更好的結果
        try:
            # 並行使用多個引擎，以獲得更多樣化的結果
            engines = ["google", "duckduckgo"]  # 使用主要引擎 
            if query_idx % 2 == 0:  # 每隔一個查詢添加Wikipedia
                engines.append("wikipedia")
            
            search_results = await searcher.search(query, engines=engines)
            if not search_results:
                logger.warning(f"未找到 {query} 的搜尋結果")
                log_chain_of_thought(state, f"未找到 '{query}' 的搜尋結果")
                return
                
        except Exception as e:
            console.print(f"[red]搜尋期間出錯：{e}[/]")
            log_chain_of_thought(state, f"搜尋 {query} 時出錯：{str(e)}")
            return
        
        # 分批過濾相關URL，以避免使LLM負荷過重
        relevant_urls = []
        url_batches = [search_results[i:i+10] for i in range(0, len(search_results), 10)]
        
        for batch in url_batches:
            if is_shutdown_requested():
                break

            relevance_tasks = []
            for result in batch:
                relevance_task = is_relevant_url(llm, result.url, result.title, result.snippet, query)
                relevance_tasks.append((result, relevance_task))
            
            # 等待此批次中的所有相關性檢查完成
            for result, relevance_task in relevance_tasks:
                try:
                    is_relevant = await relevance_task
                    if is_relevant:
                        relevant_urls.append(result)

                        state["sources"].append({
                            "url": result.url,
                            "title": result.title,
                            "snippet": result.snippet,
                            "source": result.source,
                            "query": query
                        })
                except Exception as e:
                    logger.error(f"檢查 {result.url} 的相關性時出錯：{e}")
        
        if not relevant_urls:
            log_chain_of_thought(state, f"未找到 '{query}' 的相關URL")
            return
        
        # 限制要抓取的URL數量，以提高效率
        # 選擇不同來源中最相關的URL組合
        # 首先按來源排序，以確保多樣性，然後取前N個
        relevant_urls.sort(key=lambda r: r.source)
        relevant_urls = relevant_urls[:8]  # 從5增加到8，以獲得更好的覆蓋率
        
        # 使用改進的抓取器一次性抓取相關URL
        urls_to_scrape = [result.url for result in relevant_urls]
        
        # 新的抓取器實現內部處理併發性
        # 它將使用信號量來限制併發抓取並處理超時
        try:
            scraped_contents = await scraper.scrape_urls(
                urls_to_scrape, 
                dynamic=False,  # 除非特別需要，否則避免動態抓取以提高速度 
                force_refresh=False  # 如果可用，使用緩存
            )
        except Exception as e:
            logger.error(f"抓取 {query} 的URL時出錯：{e}")
            log_chain_of_thought(state, f"抓取 {query} 的URL時出錯：{str(e)}")
            return

        processed_items = []
        successful_scrapes = [item for item in scraped_contents if item.is_successful()]

        for item in successful_scrapes:
            if is_shutdown_requested():
                break
                
            logger.info(f"處理從 {item.url} 抓取的內容")
            content_preview = item.text[:100] + "..." if len(item.text) > 100 else item.text
            logger.debug(f"內容預覽：{content_preview}")
            
            processed_item = await process_scraped_item(llm, item, query, item.text)
            processed_items.append(processed_item)
        
        if not processed_items:
            log_chain_of_thought(state, f"無法從 {query} 的URL中提取內容")
            return
        
        # 以結構化方式準備內容以供分析
        combined_content = ""
        for item in processed_items:

            combined_content += f"\n\n## 來源：{item['item'].url}\n"
            combined_content += f"## 標題：{item['item'].title or '無標題'}\n"
            combined_content += f"## 可靠性：{item['rating']}\n"
            combined_content += f"## 內容開始\n{item['content']}\n## 內容結束\n"
        
        analysis = await analyze_content(llm, query, combined_content)
        
        state["content_analysis"].append({
            "query": query,
            "sources": [item["item"].url for item in processed_items],
            "analysis": analysis
        })
        
        state["findings"] += f"\n\n## 對 {query} 的分析\n\n{analysis}\n\n"
        
        log_chain_of_thought(state, f"分析了 {query} 的內容")
        if progress_callback:
            await _call_progress_callback(progress_callback, state)

    tasks = []
    for idx, query in enumerate(recent_queries):
        tasks.append(process_query(query, idx))
    
    # 使用gather並行處理所有查詢，但有適當的控制
    await asyncio.gather(*tasks)
    
    state["current_depth"] += 1
    log_chain_of_thought(state, f"完成了 {state['depth']} 中的第 {state['current_depth']} 層")

    if progress_callback and state.get("status") != "Searching":
        state["status"] = "搜尋完成"
        await _call_progress_callback(progress_callback, state)
    
    return state
