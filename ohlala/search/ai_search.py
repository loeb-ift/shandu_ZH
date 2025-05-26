from typing import List, Dict, Optional, Any
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchRun, DuckDuckGoSearchResults
from .search import UnifiedSearcher, SearchResult
from ..config import config
from ..scraper import WebScraper, ScrapedContent
from ..agents.utils.citation_manager import CitationManager, SourceInfo

@dataclass
class AISearchResult:
    """用於AI增強搜索結果的容器，具備豐富輸出和引用追蹤功能。"""
    query: str
    summary: str
    sources: List[Dict[str, Any]]
    citation_stats: Optional[Dict[str, Any]] = None
    timestamp: datetime = datetime.now()
    
    def to_markdown(self) -> str:
        """轉換為具有更好可讀性的Markdown格式。"""
        timestamp_str = self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        md = [
            f"# {self.query}",
            "## 摘要",
            self.summary,
            "## 來源"
        ]
        for i, source in enumerate(self.sources, 1):
            title = source.get('title', '未命名')
            url = source.get('url', '')
            snippet = source.get('snippet', '')
            source_type = source.get('source', '未知')
            md.append(f"### {i}. {title}")
            if url:
                md.append(f"- **URL:** [{url}]({url})")
            if source_type:
                md.append(f"- **來源類型:** {source_type}")
            if snippet:
                md.append(f"- **摘要:** {snippet}")
            md.append("")

        if self.citation_stats:
            md.append("## 研究過程")
            md.append(f"- **分析的來源數量**: {self.citation_stats.get('total_sources', len(self.sources))}")
            md.append(f"- **關鍵信息點**: {self.citation_stats.get('total_learnings', 0)}")
            if self.citation_stats.get('source_reliability'):
                md.append(f"- **來源質量**: {len(self.citation_stats.get('source_reliability', {}))} 個域名已評估")
            md.append("")
            
        return "\n".join(md)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式。"""
        result = {
            "query": self.query,
            "summary": self.summary,
            "sources": self.sources,
            "timestamp": self.timestamp.isoformat()
        }
        if self.citation_stats:
            result["citation_stats"] = self.citation_stats
        return result

class AISearcher:
    """
    AI驅動的搜索功能。
    將搜索結果與AI分析相結合，適用於任何類型的查詢。
    具備網頁爬取能力、詳細輸出、來源引用和知識提取功能。
    """
    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        searcher: Optional[UnifiedSearcher] = None,
        scraper: Optional[WebScraper] = None,
        citation_manager: Optional[CitationManager] = None,
        max_results: int = 10,
        max_pages_to_scrape: int = 3
    ):
        api_base = config.get("api", "base_url")
        api_key = config.get("api", "api_key")
        model = config.get("api", "model")
        self.llm = llm or ChatOpenAI(
            base_url=api_base,
            api_key=api_key,
            model=model,
            temperature=0.4,
            max_tokens=8192
        )
        self.searcher = searcher or UnifiedSearcher(max_results=max_results)
        self.scraper = scraper or WebScraper()
        self.citation_manager = citation_manager or CitationManager()
        self.max_results = max_results
        self.max_pages_to_scrape = max_pages_to_scrape

        self.ddg_search = DuckDuckGoSearchRun()
        self.ddg_results = DuckDuckGoSearchResults(output_format="list")
    
    async def search(
        self, 
        query: str,
        engines: Optional[List[str]] = None,
        detailed: bool = False,
        enable_scraping: bool = True,
        use_ddg_tools: bool = True
    ) -> AISearchResult:
        """
        執行AI增強搜索，提供詳細輸出和來源引用。
        
        參數:
            query: 搜索查詢（可以是任何主題）
            engines: 要使用的搜索引擎列表
            detailed: 是否生成詳細分析
            enable_scraping: 是否從頂部結果中爬取內容
            use_ddg_tools: 是否使用langchain_community中的DuckDuckGo工具
        
        返回:
            AISearchResult對象，包含全面的摘要和引用的來源
        """
        timestamp = datetime.now()
        sources = []
        
        # 若啟用，則使用DuckDuckGo工具
        if use_ddg_tools and (not engines or 'duckduckgo' in engines):
            try:
                ddg_structured_results = self.ddg_results.invoke(query)
                for result in ddg_structured_results[:self.max_results]:
                    source_info = {
                        "title": result.get("title", "未命名"),
                        "url": result.get("link", ""),
                        "snippet": result.get("snippet", ""),
                        "source": "DuckDuckGo"
                    }
                    sources.append(source_info)
                    
                    # 向引用管理器註冊來源
                    self._register_source_with_citation_manager(source_info)
            except Exception as e:
                print(f"使用DuckDuckGoSearchResults時出錯: {e}")
        
        # 若沒有來源或未啟用DuckDuckGo工具，則使用UnifiedSearcher作為備用
        if not sources or not use_ddg_tools:
            search_results = await self.searcher.search(query, engines)
        
        # 收集所有來源
            for result in search_results:
                if isinstance(result, SearchResult):
                    result_dict = result.to_dict()
                    sources.append(result_dict)
                    
                    # 向引用管理器註冊來源
                    self._register_source_with_citation_manager(result_dict)
                elif isinstance(result, dict):
                    sources.append(result)
                    
                    # 向引用管理器註冊來源
                    self._register_source_with_citation_manager(result)
        
        # 若啟用，則爬取更多內容
        if enable_scraping:
            urls_to_scrape = []
            for source in sources:
                if source.get('url') and len(urls_to_scrape) < self.max_pages_to_scrape:
                    urls_to_scrape.append(source['url'])
            if urls_to_scrape:
                print(f"正在爬取 {len(urls_to_scrape)} 個頁面以獲取更深入的見解...")
                scraped_results = await self.scraper.scrape_urls(urls_to_scrape, dynamic=True)
                for scraped in scraped_results:
                    if hasattr(scraped, 'is_successful') and scraped.is_successful():
                        try:
                            main_content = scraped.text
                            if hasattr(self.scraper, 'extract_main_content'):
                                main_content = await self.scraper.extract_main_content(scraped)
                            if "意外錯誤" in main_content.lower():
                                continue
                            preview = main_content[:500] + ("...(截斷)" if len(main_content) > 1500 else "")
                            source_info = {
                                "title": scraped.title,
                                "url": scraped.url,
                                "snippet": preview,
                                "source": "爬取的內容"
                            }
                            sources.append(source_info)
                            
                            # 向引用管理器註冊來源並提取知識
                            source_id = self._register_source_with_citation_manager(source_info)
                            if source_id and main_content:
                                self.citation_manager.extract_learning_from_text(
                                    main_content, 
                                    scraped.url,
                                    context=f"搜索查詢: {query}"
                                )
                        except Exception as e:
                            print(f"處理來自 {scraped.url} 的爬取內容時出錯: {e}")
        
        # 準備具有改進引用格式的來源
        aggregated_text = ""
        for i, source in enumerate(sources, 1):
            url = source.get('url', '')
            domain = url.split("//")[1].split("/")[0] if "//" in url else "未知來源"
            # 將域名的首字母大寫，使其更專業
            domain_name = domain.split('.')[0].capitalize() if '.' in domain else domain
            
            aggregated_text += (
                f"[{i}] {domain_name}\n"
                f"標題: {source.get('title', '未命名')}\n"
                f"URL: {url}\n"
                f"摘要: {source.get('snippet', '')}\n\n"
            )
        
        current_date = timestamp.strftime('%Y-%m-%d')
        if detailed:
            detail_instruction = (
                "提供詳細的分析，包括深入的解釋、具體的例子、相關的背景信息和額外的見解，以增強對主題的理解。"
            )
        else:
            detail_instruction = "提供簡潔而有信息價值的摘要，重點關注關鍵點和基本信息。"
        
        final_prompt = f"""你是Ohlala，一位專家分析師。根據以下於 {current_date} 為查詢 "{query}" 檢索到的來源，{detail_instruction}

- 如果查詢是一個問題，請直接給出詳細的解釋。
- 如果是一個主題，請提供全面的概述和支持細節。
- 使用項目符號或編號列表來清晰地組織信息。
- 如果存在相互矛盾的觀點或不確定性，請明確討論。
- 提供信息時，通過使用方括號中的數字（如 [1]）來引用來源，以表明信息的來源。
- 僅使用以下來源中提供的引用編號。
- 不要在引用中包含年份或日期，只需使用方括號中的數字（如 [1]）。
- 確保回覆引人入勝、詳細，並以適合所有讀者的純文本格式撰寫。

來源:

{aggregated_text}
"""
        
        final_output = await self.llm.ainvoke(final_prompt)

        citation_stats = None
        if sources:
            citation_stats = {
                "total_sources": len(self.citation_manager.sources),
                "total_learnings": len(self.citation_manager.learnings),
                "source_reliability": self.citation_manager._calculate_source_reliability()
            }
        
        return AISearchResult(
            query=query,
            summary=final_output.content.strip(),
            sources=sources,
            citation_stats=citation_stats,
            timestamp=timestamp
        )
    
    def _register_source_with_citation_manager(self, source: Dict[str, Any]) -> Optional[str]:
        """向引用管理器註冊來源並返回其ID。"""
        try:
            url = source.get('url', '')
            if not url:
                return None
                
            title = source.get('title', '未命名')
            snippet = source.get('snippet', '')
            source_type = source.get('source', '網頁')

            domain = url.split("//")[1].split("/")[0] if "//" in url else "未知"

            source_info = SourceInfo(
                url=url,
                title=title,
                snippet=snippet,
                source_type=source_type,
                content_type="文章",
                access_time=time.time(),
                domain=domain,
                reliability_score=0.8,  # 默認分數
                metadata=source
            )

            return self.citation_manager.add_source(source_info)
            
        except Exception as e:
            print(f"向引用管理器註冊來源時出錯: {e}")
            return None
    
    def search_sync(
        self, 
        query: str,
        engines: Optional[List[str]] = None,
        detailed: bool = False,
        enable_scraping: bool = True,
        use_ddg_tools: bool = True
    ) -> AISearchResult:
        """搜索方法的同步版本。"""
        return asyncio.run(self.search(query, engines, detailed, enable_scraping, use_ddg_tools))
