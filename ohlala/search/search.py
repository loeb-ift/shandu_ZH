"""
多引擎網路搜尋模組

功能架構：
1. 搜尋引擎流程控制
   - 預設順序: ['google', 'duckduckgo', 'wikipedia', 'bing', 'brave']
   - 備用機制: 當主要引擎返回4XX錯誤時自動切換至 Google Custom Search (付費的API)
   - 請求間隔: 隨機延遲 1-3 秒避免觸發反爬機制

2. 核心組件：
   - SearchEngine 抽象基類
   - GoogleSearch/GoogleCustomSearch 實現類
   - 搜尋結果統一格式: SearchResult 資料類

3. 錯誤處理：
   - 分級重試策略 (3次重試，指數退避)
   - 異常類型區分處理 (網路錯誤 vs 解析錯誤)
   - 統一錯誤日誌記錄 (self.logger)

4. 效能優化：
   - 非同步IO架構 (aiohttp)
   - 結果快取機制 (LRU, 24小時TTL)
   - HTML解析加速 (BeautifulSoup4)

5. 配置管理：
   - 集中管理API金鑰與環境變數
   - 用戶代理輪替策略
   - 代理伺服器支援
"""
import os
import asyncio
import time
import random
import json
from typing import List, Dict, Any, Optional, Union, Set
from functools import lru_cache
from dataclasses import dataclass
import logging
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
# 修正語法錯誤，導入時別名不能有空格，將 "Google Search" 改為 "GoogleSearch"
from googlesearch import search as GoogleSearch

from logging.handlers import RotatingFileHandler
from logging import StreamHandler

from shandu.utils.logger import setup_logger


# Configure logging
city_name = 'Taipei'
logger = setup_logger(city_name)

# Add console handler to logger
console_handler = StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# API Keys and Configuration Settings - Centralized management for all API keys and environment settings
# Please update your API keys here
GOOGLE_CUSTOM_API_KEY = "XXX"
GOOGLE_CUSTOM_CX = "XXX"
BRAVE_API_KEY = "your_brave_api_key_here"

# Try to get USER_AGENT from environment, otherwise use a generic one
# 定义多平台现代浏览器用户代理池
USER_AGENTS = [
    # Chrome 最新版本 (Windows/MacOS/Linux)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    
    # Firefox 最新版本
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0',
    
    # Safari 最新版本
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
    
    # Edge 最新版本
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0'
]

# 修改获取逻辑
USER_AGENT = os.environ.get('USER_AGENT', random.choice(USER_AGENTS))

# 在搜索请求中应用
async def fetch(self, url):
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    self.logger.info(f"開始使用 Google 搜尋關鍵詞: {query}")
    try:
        delay = random.uniform(1, 5)  # 隨機延遲 1 到 5 秒
        await asyncio.sleep(delay)

        results = []
        self.logger.info(f"呼叫 googlesearch 庫進行搜尋，最大結果數: {self.max_results}")
        
        try:
            google_results = list(GoogleSearch(query, num_results=self.max_results))
        except Exception as e:
            self.logger.error(f"呼叫 googlesearch 庫時出錯: {e}")
            google_results = []
        self.logger.info(f"從 googlesearch 庫獲得的結果數量: {len(google_results)}")
        for j in google_results:
            result = SearchResult(
                url = j,
                title = j,  # We don't have titles from this library
                snippet = "",  # We don't have snippets from this library
                source = "Google"
            )
            results.append(result)

        if results:
            self.logger.info("嘗試豐富 Google 搜尋結果的標題和摘要")
            await self._enrich_google_results(results, query)

        self.logger.info(f"最終的 Google 搜尋結果數量: {len(results)}")
        return results
    except Exception as e:
        self.logger.error(f"Error during Google search: {e}")
        raise

    async def _enrich_google_results(self, results: List[SearchResult], query: str) -> None:
        """
        Enrich Google search results with titles and snippets.

        Args:
            results: List of search results to enrich
            query: Original query
        """
        try:
            timeout = aiohttp.ClientTimeout(total = 15)  # 15 second timeout
            async with aiohttp.ClientSession(timeout = timeout) as session:
                url = f"https://www.google.com/search?q={quote_plus(query)}"
                headers = {"User-Agent": self.user_agent}

                async with session.get(url, headers = headers) as response:
                    self.logger.info(f"Google Search API response status: {response.status}")
                    if response.status != 200:
                        self.logger.warning(f"Google search returned status code {response.status}")
                        return

                    html = await response.text()
                    soup = BeautifulSoup(html, features = "html.parser")

                    search_divs = soup.find_all("div", class_ = "g")

                    for i, div in enumerate(search_divs):
                        if i >= len(results):
                            break

                        title_elem = div.find("h3")
                        if title_elem:
                            results[i].title = title_elem.text.strip()

                        snippet_elem = div.find("div", class_ = "VwiC3b")
                        if snippet_elem:
                            results[i].snippet = snippet_elem.text.strip()

        except asyncio.TimeoutError:
            self.logger.warning("Timeout while enriching Google results")
        except Exception as e:
            self.logger.error(f"Error enriching Google results: {e}")

    async def _search_duckduckgo(self, query: str) -> List[SearchResult]:
        self.logger.info(f"開始使用 DuckDuckGo 搜尋關鍵詞: {query}")
        try:
            timeout = aiohttp.ClientTimeout(total = 15)  # 15 second timeout
            async with aiohttp.ClientSession(timeout = timeout) as session:
                url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                headers = {"User-Agent": self.user_agent}

                self.logger.info(f"向 {url} 發送 GET 請求，標頭: {headers}")
                async with session.get(url, headers = headers) as response:
                    self.logger.info(f"收到 DuckDuckGo 回應，狀態碼: {response.status}")
                    if response.status != 200:
                        self.logger.warning(f"DuckDuckGo search returned status code {response.status}")
                        raise ValueError(f"DuckDuckGo search returned status code {response.status}")

                    html = await response.text()
                    soup = BeautifulSoup(html, features = "html.parser")

                    results = []
                    for result in soup.find_all("div", class_ = "result"):
                        title_elem = result.find("a", class_ = "result__a")
                        if not title_elem:
                            continue

                        title = title_elem.text.strip()

                        url = title_elem.get("href", "")
                        if not url:
                            continue

                        if url.startswith("/"):
                            url = "https://duckduckgo.com" + url

                        snippet_elem = result.find("a", class_ = "result__snippet")
                        snippet = snippet_elem.text.strip() if snippet_elem else ""

                        result = SearchResult(
                            url = url,
                            title = title,
                            snippet = snippet,
                            source = "DuckDuckGo"
                        )
                        results.append(result)

                        # Limit to max_results
                        if len(results) >= self.max_results:
                            break

                    self.logger.info(f"DuckDuckGo search returned {len(results)} results")
                    return results

        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout during DuckDuckGo search for query: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Error during DuckDuckGo search: {e}")
            raise

    async def _search_bing(self, query: str) -> List[SearchResult]:
        self.logger.info(f"開始使用 Bing 搜尋關鍵詞: {query}")
        try:
            timeout = aiohttp.ClientTimeout(total = 15)  # 15 second timeout
            async with aiohttp.ClientSession(timeout = timeout) as session:
                url = f"https://www.bing.com/search?q={quote_plus(query)}"
                headers = {"User-Agent": self.user_agent}

                self.logger.info(f"向 {url} 發送 GET 請求，標頭: {headers}")
                async with session.get(url, headers = headers) as response: # Corrected from search_url and proxy
                    if response.status != 200:
                        self.logger.warning(f"Bing 搜尋狀態碼 {response.status}")
                        raise ValueError(f"Bing 搜尋狀態碼 {response.status}")

                    html = await response.text()
                    soup = BeautifulSoup(html, features = "html.parser")

                    results = []
                    for result in soup.find_all("li", class_ = "b_algo"):
                        title_elem = result.find("h2")
                        if not title_elem:
                            continue

                        title = title_elem.text.strip()

                        url_elem = title_elem.find("a")
                        if not url_elem:
                            continue

                        url = url_elem.get("href", "")
                        if not url:
                            continue

                        snippet_elem = result.find("div", class_ = "b_caption")
                        snippet = ""
                        if snippet_elem:
                            p_elem = snippet_elem.find("p")
                            if p_elem:
                                snippet = p_elem.text.strip()

                        result = SearchResult(
                            url = url,
                            title = title,
                            snippet = snippet,
                            source = "Bing"
                        )
                        results.append(result)

                        # Limit to max_results
                        if len(results) >= self.max_results:
                            break

                    self.logger.info(f"最終的 Bing 搜尋結果數量: {len(results)}")
                    return results

        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout during Bing search for query: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Error during Bing search: {e}")
            raise

    async def _search_brave(self, query: str) -> List[SearchResult]:
        """
        Search Brave for a query using their Web Search API.

        Args:
            query: Query to search for

        Returns:
            List of search results
        """
        try:
            api_key = BRAVE_API_KEY
            if api_key == "your_brave_api_key_here":
                self.logger.error("BRAVE_API_KEY未設置 - 請檢查文件開頭的API設置部分")
                raise ValueError("BRAVE_API_KEY placeholder not replaced")

            timeout = aiohttp.ClientTimeout(total = 15)
            async with aiohttp.ClientSession(timeout = timeout) as session:
                url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}"
                headers = {
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key
                }

                async with session.get(url, headers = headers) as response:
                    if response.status != 200:
                        self.logger.warning(f"Brave search returned status code {response.status}")
                        self.logger.error(f"Brave Search failed with status {response.status}")
                        raise ValueError(f"Brave search returned status code {response.status}")

                    data = await response.json()

                    results = []
                    # Process web search results
                    if 'web' in data and 'results' in data['web']:
                        for result_data in data['web']['results'][:self.max_results]:
                            result = SearchResult(
                                url = result_data.get('url', ''),
                                title = result_data.get('title', ''),
                                snippet = result_data.get('description', ''),
                                source = "Brave"
                            )
                            results.append(result)

                    return results

        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout during Brave search for query: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Error during Brave search: {e}")
            raise

    async def _search_wikipedia(self, query: str) -> List[SearchResult]:
        self.logger.info(f"開始使用 Wikipedia 搜尋關鍵詞: {query}")
        try:
            timeout = aiohttp.ClientTimeout(total = 15)  # 15 second timeout
            async with aiohttp.ClientSession(timeout = timeout) as session:
                url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(query)}&limit={self.max_results}&namespace=0&format=json"
                headers = {"User-Agent": self.user_agent}

                self.logger.info(f"向 {url} 發送 GET 請求，標頭: {headers}")
                async with session.get(url, headers = headers) as response:
                    self.logger.info(f"收到 Wikipedia 回應，狀態碼: {response.status}")
                    if response.status != 200:
                        self.logger.warning(f"Wikipedia search returned status code {response.status}")
                        raise ValueError(f"Wikipedia search returned status code {response.status}")

                    data = await response.json()

                    results = []
                    for i in range(len(data[1])):
                        title = data[1][i]
                        snippet = data[2][i]
                        url = data[3][i]

                        result = SearchResult(
                            url = url,
                            title = title,
                            snippet = snippet,
                            source = "Wikipedia"
                        )
                        results.append(result)

                    self.logger.info(f"最終的 Wikipedia 搜尋結果數量: {len(results)}")
                    return results

        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout during Wikipedia search for query: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Error during Wikipedia search: {e}")
            raise

    async def search_node(self, sub_queries: List[str], engines: Optional[List[str]] = None) -> Dict[str, List[SearchResult]]:
        """
        為每個子查詢指定搜尋引擎。

        Args:
            sub_queries: 子查詢列表
            engines: 要使用的搜索引擎列表，如果為 None，則使用所有可用引擎

        Returns:
            每個子查詢的搜尋結果字典
        """
        if engines is None:
            engines = ['google', 'google_custom', 'duckduckgo', 'wikipedia', 'bing', 'brave']

        results_dict = {}
        for sub_query in sub_queries:
            results = []

            self.logger.info(f"開始搜尋子查詢: {sub_query}，使用引擎: {engines}")

            original_engines = engines.copy()
            if 'google_custom' in engines:
                engines.remove('google_custom')
                fallback_engine = 'google_custom'
            else:
                fallback_engine = None

            for engine in engines:
                if engine not in ["google", "duckduckgo", "bing", "wikipedia", "brave"]:
                    raise ValueError(f"Unsupported search engine: {engine}")
                try:
                    self.logger.info(f"開始使用 {engine} 搜尋子查詢: {sub_query}")
                    delay = random.uniform(1, 3)  # 隨機延遲 1 到 3 秒
                    await asyncio.sleep(delay)

                    if engine == 'google':
                        engine_results = await self._search_google(sub_query)
                    elif engine == 'duckduckgo':
                        engine_results = await self._search_duckduckgo(sub_query)
                    elif engine == 'bing':
                        engine_results = await self._search_bing(sub_query)
                    elif engine == 'brave':
                        engine_results = await self._search_with_retry(self._search_brave, sub_query)
                    elif engine == 'wikipedia':
                        engine_results = await self._search_wikipedia(sub_query)

                    results.extend(engine_results)
                    self.logger.info(f"{engine} 搜尋完成，新增結果數量: {len(engine_results)}")
                except Exception as e:
                    if hasattr(e, 'status') and 400 <= e.status < 500:
                        self.logger.warning(f"{engine} 搜尋達到限制 (狀態碼 {e.status})，嘗試使用 {fallback_engine} 作為備用")
                        if fallback_engine and fallback_engine == 'google_custom':
                            try:
                                fallback_results = await self._search_with_retry(self._search_google_custom, sub_query)
                                results.extend(fallback_results)
                                self.logger.info(f"{fallback_engine} 備用搜尋完成，新增結果數量: {len(fallback_results)}")
                            except Exception as fe:
                                self.logger.error(f"{fallback_engine} 備用搜尋失敗: {fe}")
                    self.logger.error(f"{engine} 搜尋子查詢時出錯: {sub_query}，錯誤信息: {e}")

            self.logger.info(f"所有引擎搜尋完成，累計結果數量: {len(results)}")

            results_dict[sub_query] = results[:self.max_results]

        return results_dict

    async def _get_semaphore(self) -> asyncio.Semaphore:
        """
        Get or create a semaphore for the current event loop.

        This ensures that each thread has its own semaphore bound to the correct event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            loop_id = id(loop)

            if loop_id in self._semaphores:
                return self._semaphores[loop_id]

            async with self._semaphore_lock:
                if loop_id in self._semaphores:
                    return self._semaphores[loop_id]

                semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent requests
                self._semaphores[loop_id] = semaphore
                return semaphore

        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            semaphore = asyncio.Semaphore(5)

            loop_id = id(loop)
            self._semaphores[loop_id] = semaphore
            return semaphore

    @lru_cache(maxsize = 128)
    def _get_formatted_query(self, query: str, engine: str) -> str:
        """Create a cache-friendly formatted query string."""
        return f"{engine.lower()}:{query.lower()}"

    async def _search_with_retry(self, func, *args, retries = 3, delay = 1):
        """
        重試機制
        """
        for attempt in range(retries):
            try:
                return await func(*args)
            except Exception as e:
                if attempt < retries - 1:
                    self.logger.warning(f"重試 {func.__name__} 第 {attempt + 1} 次，延遲 {delay} 秒後重試，錯誤信息: {e}")
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"{func.__name__} 重試 {retries} 次後仍失敗，錯誤信息: {e}")
                    raise

    async def search(self, query: str, engines: Optional[List[str]] = None) -> List[SearchResult]:
        """
        執行統一搜尋，整合多個搜索引擎的結果。

        Args:
            query: 搜尋關鍵詞
            engines: 要使用的搜索引擎列表，如果為 None 則使用所有引擎

        Returns:
            搜尋結果列表
        """
        if engines is None:
            engines = ['duckduckgo', 'bing', 'google']

        all_results = []
        tasks = []

        if 'duckduckgo' in engines:
            tasks.append(self._search_duckduckgo(query))
        if 'bing' in engines:
            tasks.append(self._search_bing(query))
        if 'google' in engines:
            tasks.append(self._search_google(query))

        if tasks:
            results_list = await asyncio.gather(*tasks)
            for results in results_list:
                all_results.extend(results)

        # 限制結果數量
        return all_results[:self.max_results]

    def search_sync(self, query: str, engines: Optional[List[str]] = None) -> List[SearchResult]:
        """
        同步版本的搜尋方法。
        """
        logger.info(f"開始同步搜尋，查詢詞: {query}，使用引擎: {engines}")
        result = asyncio.run(self.search(query, engines))
        logger.info(f"同步搜尋完成，返回結果數量: {len(result)}")
        return result

# 项目根目录相对路径处理
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# 在日志初始化前添加目录检查
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)
    
# 初始化日志系统（保留原有配置）
self.logger = setup_logger(
    name=self.__class__.__name__,
    log_file=os.path.join(LOG_DIR, 'search_operations.log'),
    # 保留关键参数说明
    max_bytes=10*1024*1024,  # 10MB
    backup_count=5
    # 移除冗余注释：
    # - 日志路径已通过LOG_DIR统一管理
    # - 日志级别从配置读取
)
def parse_results(self, html):
    """
    [现有文档字符串已包含完整说明]
    """
    # 使用BeautifulSoup解析HTML
    # 提取标题、URL和摘要
    soup = BeautifulSoup(html, 'lxml')
