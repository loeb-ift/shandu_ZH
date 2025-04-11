"""閃度研究系統的代理模塊。"""
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio
import json
import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
from langchain.agents import AgentType, initialize_agent
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_community.tools import Tool, DuckDuckGoSearchResults, DuckDuckGoSearchRun

from ..search.search import UnifiedSearcher, SearchResult
from ..research.researcher import ResearchResult
from ..scraper import WebScraper, ScrapedContent
from ..prompts import SYSTEM_PROMPTS, USER_PROMPTS
from .utils.citation_manager import CitationManager, SourceInfo, Learning

class ResearchAgent:
    """基於LangChain的研究代理，具備增強的引用追蹤功能。"""
    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        searcher: Optional[UnifiedSearcher] = None,
        scraper: Optional[WebScraper] = None,
        temperature: float = 0,
        max_depth: int = 2,
        breadth: int = 4,
        max_urls_per_query: int = 3,
        proxy: Optional[str] = None
    ):
        self.llm = llm or ChatOpenAI(
            temperature=temperature,
            model="gpt-4"
        )
        self.searcher = searcher or UnifiedSearcher()
        self.scraper = scraper or WebScraper(proxy=proxy)
        self.citation_manager = CitationManager()  # 初始化引用管理器
        # 研究參數
        self.max_depth = max_depth
        self.breadth = breadth
        self.max_urls_per_query = max_urls_per_query

        self.system_prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPTS["research_agent"])
        self.reflection_prompt = ChatPromptTemplate.from_template(USER_PROMPTS["reflection"])
        self.query_gen_prompt = ChatPromptTemplate.from_template(USER_PROMPTS["query_generation"])

        self.tools = self._setup_tools()

        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True
        )

    def _setup_tools(self) -> List[Tool]:
        """設置代理工具。"""
        return [
            Tool(
                name="search",
                func=self.searcher.search_sync,
                description="從多個來源搜索有關某個主題的信息"
            ),
            DuckDuckGoSearchResults(
                name="ddg_results",
                description="從DuckDuckGo獲取詳細的搜索結果"
            ),
            DuckDuckGoSearchRun(
                name="ddg_search",
                description="在DuckDuckGo上快速搜索答案"
            ),
            Tool(
                name="reflect",
                func=self._reflect_on_findings,
                description="分析和反思當前的研究結果"
            ),
            Tool(
                name="generate_queries",
                func=self._generate_subqueries,
                description="生成有針對性的子查詢以進行更深入的研究"
            )
        ]

    async def _reflect_on_findings(self, findings: str) -> str:
        """分析研究結果。"""
        reflection_chain = self.reflection_prompt | self.llm | StrOutputParser()
        return await reflection_chain.ainvoke({"findings": findings})

    async def _generate_subqueries(
        self,
        query: str,
        findings: str,
        questions: str
    ) -> List[str]:
        """生成子查詢以進行更深入的研究。"""
        query_chain = self.query_gen_prompt | self.llm | StrOutputParser()
        result = await query_chain.ainvoke({
            "query": query,
            "findings": findings,
            "questions": questions,
            "breadth": self.breadth
        })

        queries = [q.strip() for q in result.split("\n") if q.strip()]
        return queries[:self.breadth]

    async def _extract_urls_from_results(
        self,
        search_results: List[SearchResult],
        max_urls: int = 3
    ) -> List[str]:
        """從搜索結果中提取頂部URL。"""
        urls = []
        seen = set()
        
        for result in search_results:
            if len(urls) >= max_urls:
                break
                
            url = result.url
            if url and url not in seen and url.startswith('http'):
                urls.append(url)
                seen.add(url)
        
        return urls

    async def _analyze_content(
        self,
        query: str,
        content: List[ScrapedContent]
    ) -> Dict[str, Any]:
        """分析爬取的內容，並使用引用管理器追蹤學習內容。"""
        # 準備用於分析的內容
        content_text = ""
        for item in content:

            source_info = SourceInfo(
                url=item.url,
                title=item.title,
                content_type=item.content_type,
                access_time=time.time(),
                domain=item.url.split("//")[1].split("/")[0] if "//" in item.url else "unknown",
                reliability_score=0.8,  # 預設分數，可更動態化
                metadata=item.metadata
            )
            self.citation_manager.add_source(source_info)

            content_text += f"\n來源: {item.url}\n標題: {item.title}\n"
            content_text += f"內容摘要:\n{item.text[:2000]}...\n"
        
        # 使用集中式提示中的內容分析提示
        analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPTS["content_analysis"]),
            ("user", USER_PROMPTS["content_analysis"])
        ])
        
        analysis_chain = analysis_prompt | self.llm | StrOutputParser()
        analysis = await analysis_chain.ainvoke({"query": query, "content": content_text})

        for item in content:
            # 使用引用管理器提取並註冊學習內容
            learning_hashes = self.citation_manager.extract_learning_from_text(
                analysis,  # 使用分析結果作為學習內容的來源
                item.url,
                context=f"針對查詢的分析: {query}"
            )
            
        return {
            "分析": analysis,
            "來源": [c.url for c in content],
            "學習內容數量": len(self.citation_manager.learnings)  # 追蹤學習內容的數量
        }

    async def research(
        self,
        query: str,
        depth: Optional[int] = None,
        engines: List[str] = ["google", "duckduckgo"]
    ) -> ResearchResult:
        """執行具有增強引用追蹤功能的研究過程。"""
        depth = depth if depth is not None else self.max_depth

        context = {
            "查詢": query,
            "深度": depth,
            "寬度": self.breadth,
            "研究結果": "",
            "來源": [],
            "子查詢": [],
            "內容分析": [],
            "按來源劃分的學習內容": {}  # 按來源追蹤學習內容
        }
        
        # 初始系統提示以設置研究
        system_chain = self.system_prompt | self.llm | StrOutputParser()
        context["研究結果"] = await system_chain.ainvoke(context)
        
        # 迭代深化研究過程
        for current_depth in range(depth):
            # 反思當前的研究結果
            reflection = await self._reflect_on_findings(context["研究結果"])
            
            new_queries = await self._generate_subqueries(
                query=query,
                findings=context["研究結果"],
                questions=reflection
            )
            context["子查詢"].extend(new_queries)
            
            for subquery in new_queries:
                agent_result = await self.agent.arun(
                    f"研究這個特定方面: {subquery}\n\n"
                    f"當前的研究結果: {context['研究結果']}\n\n"
                    "逐步思考要使用的工具以及如何驗證信息。"
                )
                
                # 執行搜索
                search_results = await self.searcher.search(
                    subquery,
                    engines=engines
                )

                urls_to_scrape = await self._extract_urls_from_results(
                    search_results,
                    self.max_urls_per_query
                )
                
                # 爬取並分析內容
                if urls_to_scrape:
                    scraped_content = await self.scraper.scrape_urls(
                        urls_to_scrape,
                        dynamic=True,
                        force_refresh=False  # 可用時使用緩存
                    )
                    
                    if scraped_content:
                        # 分析內容
                        analysis = await self._analyze_content(subquery, scraped_content)
                        context["內容分析"].append({
                            "子查詢": subquery,
                            "分析": analysis["分析"],
                            "來源": analysis["來源"],
                            "學習內容數量": analysis.get("學習內容數量", 0)
                        })

                for r in search_results:
                    if isinstance(r, SearchResult):
                        context["來源"].append(r.to_dict())
                    elif isinstance(r, dict):
                        context["來源"].append(r)
                    else:
                        print(f"警告: 跳過不可序列化的搜索結果: {type(r)}")
                
                context["研究結果"] += f"\n\n'{subquery}'的研究結果:\n{agent_result}"

                if context["內容分析"]:
                    latest_analysis = context["內容分析"][-1]
                    context["研究結果"] += f"\n\n詳細分析:\n{latest_analysis['分析']}"
        
        # 最終反思和總結
        final_reflection = await self._reflect_on_findings(context["研究結果"])
        
        # 準備包含內容分析的詳細來源
        detailed_sources = []
        for source in context["來源"]:
            # 此時來源已經是字典
            source_dict = source.copy()  # 複製一份以避免修改原始字典

            for analysis in context["內容分析"]:
                if source.get("url", "") in analysis["來源"]:
                    source_dict["詳細分析"] = analysis["分析"]

            if source.get("url") in self.citation_manager.source_to_learnings:
                source_url = source.get("url")
                learning_ids = self.citation_manager.source_to_learnings.get(source_url, [])
                source_dict["追蹤的學習內容數量"] = len(learning_ids)
                context["按來源劃分的學習內容"][source_url] = len(learning_ids)
                
            detailed_sources.append(source_dict)

        citation_stats = {
            "總來源數量": len(self.citation_manager.sources),
            "總學習內容數量": len(self.citation_manager.learnings),
            "來源可靠性": self.citation_manager._calculate_source_reliability()
        }
        
        return ResearchResult(
            query=query,
            summary=final_reflection,
            sources=detailed_sources,
            subqueries=context["子查詢"],
            depth=depth,
            content_analysis=context["內容分析"],
            citation_stats=citation_stats
        )

    def research_sync(
        self,
        query: str,
        depth: Optional[int] = None,
        engines: List[str] = ["google", "duckduckgo"]
    ) -> ResearchResult:
        """同步研究的包裝函數。"""
        return asyncio.run(self.research(query, depth, engines))
