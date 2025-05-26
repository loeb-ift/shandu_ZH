"""
研究代理的內容處理工具。
包含處理搜索結果、提取內容和分析信息的功能。
"""
import os
from typing import List, Dict, Optional, Any, Union, TypedDict, Sequence
from dataclasses import dataclass
import json
import time
import asyncio
import re
from datetime import datetime
from rich.console import Console
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from ...search.search import SearchResult
from ...scraper import WebScraper, ScrapedContent

console = Console()

class AgentState(TypedDict):
    messages: Sequence[Union[HumanMessage, AIMessage]]
    query: str
    depth: int
    breadth: int
    current_depth: int
    findings: str
    sources: List[Dict[str, Any]]
    selected_sources: List[str]
    formatted_citations: str
    subqueries: List[str]
    content_analysis: List[Dict[str, Any]]
    start_time: float
    chain_of_thought: List[str]
    status: str
    current_date: str
    detail_level: str
    identified_themes: str
    initial_report: str
    enhanced_report: str
    final_report: str

# 結構化輸出模型
class UrlRelevanceResult(BaseModel):
    """用於URL相關性檢查的結構化輸出。"""
    is_relevant: bool = Field(description="URL是否與查詢相關")
    reason: str = Field(description="相關性決策的原因")

class ContentRating(BaseModel):
    """用於內容可靠性評級的結構化輸出。"""
    rating: str = Field(description="可靠性評級：高、中或低")
    justification: str = Field(description="評級的理由")
    extracted_content: str = Field(description="從來源中提取的相關內容")

class ContentAnalysis(BaseModel):
    """用於內容分析的結構化輸出。"""
    key_findings: List[str] = Field(description="從內容中提取的關鍵發現列表")
    main_themes: List[str] = Field(description="在內容中識別的主要主題")
    analysis: str = Field(description="對內容的全面分析")
    source_evaluation: str = Field(description="對來源可信度和相關性的評估")

async def is_relevant_url(llm: ChatOpenAI, url: str, title: str, snippet: str, query: str) -> bool:
    """
    使用結構化輸出檢查URL是否與查詢相關。
    """
    # 首先使用簡單的啟發式方法，避免對明顯不相關的域名進行LLM調用
    irrelevant_domains = [
        "pinterest", "instagram", "facebook", "twitter", "youtube", "tiktok",
        "reddit", "quora", "linkedin", "amazon.com", "ebay.com", "etsy.com",
        "walmart.com", "target.com"
    ]
    if any(domain in url.lower() for domain in irrelevant_domains):
        return False

    # 轉義輸入中的任何字面大括號，以避免格式字符串錯誤
    safe_url = url.replace("{", "{{").replace("}", "}}")
    safe_title = title.replace("{", "{{").replace("}", "}}")
    safe_snippet = snippet.replace("{", "{{").replace("}", "}}")
    safe_query = query.replace("{", "{{").replace("}", "}}")
    
    # 使用結構化輸出進行相關性檢查
    structured_llm = llm.with_structured_output(UrlRelevanceResult)
    system_prompt = (
        "你正在評估搜索結果與特定查詢的相關性。\n\n"
        "判斷搜索結果是否與回答查詢相關。\n"
        "考慮標題、URL和摘要來做出判斷。\n\n"
        "提供一個包含決策和理由的結構化回覆。\n"
    )
    user_content = (
        f"查詢：{safe_query}\n\n"
        f"搜索結果：\n標題：{safe_title}\nURL：{safe_url}\n摘要：{safe_snippet}\n\n"
        "這個結果是否與查詢相關？"
    )
    # 通過將提示管道輸入到結構化LLM中來構建提示鏈。
    prompt = ChatPromptTemplate.from_messages([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ])
    mapping = {"query": query, "title": title, "url": url, "snippet": snippet}
    try:
        # 鏈接提示和結構化LLM；然後使用映射調用invoke
        chain = prompt | structured_llm
        result = await chain.ainvoke(mapping)
        return result.is_relevant
    except Exception as e:
            from ....utils.logger import log_error
        log_error("結構化相關性檢查時發生錯誤", e, 
                 context=f"查詢：{query}, 函數：is_relevant_url")
        console.print(f"[dim red]結構化相關性檢查時發生錯誤：{str(e)}。使用簡單方法。[/dim red]")
        # 轉義回退提示中的任何字面大括號
        safe_fb_url = url.replace("{", "{{").replace("}", "}}")
        safe_fb_title = title.replace("{", "{{").replace("}", "}}")
        safe_fb_snippet = snippet.replace("{", "{{").replace("}", "}}")
        safe_fb_query = query.replace("{", "{{").replace("}", "}}")
        
        simple_prompt = (
            f"評估這個搜索結果是否與查詢相關。\n"
            "僅用「相關」或「不相關」回答。\n\n"
            f"查詢：{safe_fb_query}\n"
            f"標題：{safe_fb_title}\n"
            f"URL：{safe_fb_url}\n"
            f"摘要：{safe_fb_snippet}"
        )
        response = await llm.ainvoke(simple_prompt)
        result_text = response.content
        return "相關" in result_text.upper()

async def process_scraped_item(llm: ChatOpenAI, item: ScrapedContent, subquery: str, main_content: str) -> Dict[str, Any]:
    """
    使用結構化輸出處理爬取的項目，以評估可靠性並提取內容。
    """
    try:
        # 轉義內容中的任何字面大括號，以避免格式字符串錯誤
        safe_content = main_content[:8000].replace("{", "{{").replace("}", "}}")
        safe_url = item.url.replace("{", "{{").replace("}", "}}")
        safe_title = item.title.replace("{", "{{").replace("}", "}}")
        safe_subquery = subquery.replace("{", "{{").replace("}", "}}")
        
        structured_llm = llm.with_structured_output(ContentRating)
        system_prompt = (
            "你正在分析網頁內容的可靠性，並提取最相關的信息。\n\n"
            "使用以下標準評估內容的可靠性：\n"
            "1. 來源的可信度和專業知識\n"
            "2. 證據的質量\n"
            "3. 與已知事實的一致性\n"
            "4. 發佈日期的新近性\n"
            "5. 是否存在引用或參考文獻\n\n"
            "將來源評為「高」、「中」或「低」可靠性，並提供簡要理由。\n\n"
            "然後，提取與查詢最相關和最有價值的內容。\n"
        )
        user_message = (
            f"分析此網頁內容：\n\n"
            f"URL：{safe_url}\n"
            f"標題：{safe_title}\n"
            f"查詢：{safe_subquery}\n\n"
            "內容：\n"
            f"{safe_content}"
        )
        prompt = ChatPromptTemplate.from_messages([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ])
        mapping = {"url": item.url, "title": item.title, "subquery": subquery}
        # 將提示與結構化LLM鏈接起來
        chain = prompt | structured_llm
        result = await chain.ainvoke(mapping)
        return {
            "item": item,
            "rating": result.rating,
            "justification": result.justification,
            "content": result.extracted_content
        }
    except Exception as e:
        from ....utils.logger import log_error
        log_error("結構化內容處理時發生錯誤", e, 
                 context=f"查詢：{subquery}, 函數：process_scraped_item")
        console.print(f"[dim red]結構化內容處理時發生錯誤：{str(e)}。使用簡單方法。[/dim red]")
        current_file = os.path.basename(__file__)
        # 轉義回退內容中的任何字面大括號
        safe_shorter_content = main_content[:5000].replace("{", "{{").replace("}", "}}")
        safe_fb_url = item.url.replace("{", "{{").replace("}", "}}")
        safe_fb_title = item.title.replace("{", "{{").replace("}", "}}")
        safe_fb_subquery = subquery.replace("{", "{{").replace("}", "}}")
        
        simple_prompt = (
            f"分析網頁內容的可靠性（高/中/低）並提取相關信息。\n"
            "以以下格式回覆：\n"
            "可靠性：[評級]\n"
            "理由：[簡要解釋]\n"
            "提取的內容：[相關內容]\n\n"
            f"URL：{safe_fb_url}\n"
            f"標題：{safe_fb_title}\n"
            f"查詢：{safe_fb_subquery}\n\n"
            "內容：\n"
            f"{safe_shorter_content}"
        )
        response = await llm.ainvoke(simple_prompt)
        content = response.content
        rating = "中"  # 默認回退評級
        justification = ""
        extracted_content = content

        if "可靠性：" in content:
            reliability_match = re.search(r"可靠性：\s*(高|中|低)", content)
            if reliability_match:
                rating = reliability_match.group(1)
        if "理由：" in content:
            justification_match = re.search(r"理由：\s*(.+?)(?=\n\n|提取的內容：|$)", content, re.DOTALL)
            if justification_match:
                justification = justification_match.group(1).strip()
        if "提取的內容：" in content:
            content_match = re.search(r"提取的內容：\s*(.+?)(?=$)", content, re.DOTALL)
            if content_match:
                extracted_content = content_match.group(1).strip()

        return {
            "item": item,
            "rating": rating,
            "justification": justification,
            "content": extracted_content
        }

async def analyze_content(llm: ChatOpenAI, subquery: str, content_text: str) -> str:
    """
    使用結構化輸出分析來自多個來源的內容並綜合信息。
    """
    try:
        structured_llm = llm.with_structured_output(ContentAnalysis)
        system_prompt = (
            "你正在分析和綜合來自多個網頁來源的信息。\n\n"
            "你的任務是：\n"
            "1. 識別與查詢最相關和最重要的信息\n"
            "2. 提取關鍵發現和主要主題\n"
            "3. 將信息組織成一個連貫的分析\n"
            "4. 評估來源的可信度和相關性\n"
            "5. 在呈現事實或主張時保持來源歸屬\n\n"
            "創建一個全面、結構良好的分析，捕捉最有價值的見解。\n"
        )
        user_message = (
            f"分析以下與查詢相關的內容：「{subquery}」\n\n"
            f"{content_text}\n\n"
            "提供一個全面的分析，綜合這些來源中最相關的信息，並以結構良好的格式組織，包含關鍵發現。"
        )
        # 轉義內容中的任何字面大括號，以避免格式字符串錯誤
        system_prompt_escaped = system_prompt.replace("{", "{{").replace("}", "}}")
        user_message_escaped = user_message.replace("{", "{{").replace("}", "}}")
        
        prompt = ChatPromptTemplate.from_messages([
            {"role": "system", "content": system_prompt_escaped},
            {"role": "user", "content": user_message_escaped}
        ])
        mapping = {"query": subquery}
        # 將提示與結構化LLM鏈接起來（如有需要，使用修改後的配置）
        chain = prompt | structured_llm.with_config({"timeout": 180})
        result = await chain.ainvoke(mapping)
        formatted_analysis = "### 關鍵發現\n\n"
        for i, finding in enumerate(result.key_findings, 1):
            formatted_analysis += f"{i}. {finding}\n"
        formatted_analysis += "\n### 主要主題\n\n"
        for i, theme in enumerate(result.main_themes, 1):
            formatted_analysis += f"{i}. {theme}\n"
        formatted_analysis += f"\n### 分析\n\n{result.analysis}\n"
        formatted_analysis += f"\n### 來源評估\n\n{result.source_evaluation}\n"
        return formatted_analysis
    except Exception as e:
        from ....utils.logger import log_error
        log_error("結構化內容分析時發生錯誤", e, 
                 context=f"查詢：{subquery}, 函數：analyze_content")
        console.print(f"[dim red]結構化內容分析時發生錯誤：{str(e)}。使用簡單方法。[/dim red]")
        # 轉義回退內容中的任何字面大括號
        safe_ac_subquery = subquery.replace("{", "{{").replace("}", "}}")
        safe_ac_content = content_text[:5000].replace("{", "{{").replace("}", "}}")
        
        simple_prompt = (
            f"分析和綜合來自多個網頁來源的信息。\n"
            "提供一個簡明但全面的內容分析，與查詢相關。\n\n"
            f"分析與以下查詢相關的內容：{safe_ac_subquery}\n\n"
            f"{safe_ac_content}"
        )
        simple_llm = llm.with_config({"timeout": 60})
        response = await simple_llm.ainvoke(simple_prompt)
        return response.content
