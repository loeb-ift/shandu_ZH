"""
搜尋模組，用於 Ohlala研究系統。
提供使用各種搜尋引擎進行網路搜尋的功能。
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
from googlesearch import search as google_search

# 設置日誌檔案的路徑
log_dir = os.path.join(os.getcwd(), 'log')  # 獲取當前工作目錄並創建 log 資料夾的路徑
if not os.path.exists(log_dir):
    os.makedirs(log_dir)  # 如果資料夾不存在，則創建它

log_file_path = os.path.join(log_dir, 'search.log')  # 設定日誌檔案的完整路徑

# 配置日誌
logging.basicConfig(filename=log_file_path, level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 嘗試從環境變數獲取 USER_AGENT，否則使用通用的 USER_AGENT
USER_AGENT = os.environ.get('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

# 快取設置
CACHE_ENABLED = True
CACHE_DIR = os.path.expanduser("~/.shandu/cache/search")
CACHE_TTL = 86400  # 快取的有效時間（秒），這裡設置為 24 小時

# 如果啟用快取且快取目錄不存在，則創建目錄
if CACHE_ENABLED and not os.path.exists(CACHE_DIR):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"無法創建快取目錄: {e}")
        CACHE_ENABLED = False

@dataclass
class SearchResult:
    """用於存儲搜尋結果的類別。"""
    url: str
    title: str
    snippet: str
    source: str
    
    def __str__(self) -> str:
        """搜尋結果的字串表示。"""
        return f"標題: {self.title}\n網址: {self.url}\n摘要: {self.snippet}\n來源: {self.source}"
        
    def to_dict(self) -> Dict[str, Any]:
        """將搜尋結果轉換為字典格式。"""
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source
        }

class UnifiedSearcher:
    """統一搜尋引擎，可以使用多個搜尋引擎，並提高並行性和快取功能。"""
    
    def __init__(self, max_results: int = 10, cache_enabled: bool = CACHE_ENABLED, cache_ttl: int = CACHE_TTL):
        """
        初始化統一搜尋器。
        
        參數:
            max_results: 每個引擎返回的最大結果數量
            cache_enabled: 是否使用搜尋結果的快取
            cache_ttl: 快取內容的有效時間（秒）
        """
        self.max_results = max_results
        self.user_agent = USER_AGENT
        self.default_engine = "google"  # 設置默認引擎
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self.in_progress_queries: Set[str] = set()  # 跟蹤正在處理的查詢，以防止重複
        self._semaphores = {}  # 存儲每個事件循環的信號量字典
        self._semaphore_lock = asyncio.Lock()  # 用於線程安全訪問信號量的鎖
        
        # 嘗試使用 fake_useragent，如果可用的話
        try:
            ua = UserAgent()
            self.user_agent = ua.random
        except Exception as e:
            logger.warning(f"無法生成隨機用戶代理: {e}. 使用默認值。")
    
    async def _check_cache(self, query: str, engine: str) -> Optional[List[SearchResult]]:
        """檢查快取中是否有可用的搜尋結果且未過期。"""
        if not self.cache_enabled:
            return None
            
        cache_key = f"{engine}_{query}".replace(" ", "_").replace("/", "_").replace(".", "_")
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
        
        if not os.path.exists(cache_path):
            return None
            
        try:
            if time.time() - os.path.getmtime(cache_path) > self.cache_ttl:
                return None
                
            # 加載快取內容
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            results = []
            for item in data:
                results.append(SearchResult(
                    url=item["url"],
                    title=item["title"],
                    snippet=item["snippet"],
                    source=item["source"]
                ))
            return results
        except Exception as e:
            logger.warning(f"加載 {engine} 的 {query} 快取時出錯: {e}")
            return None
    
    async def _save_to_cache(self, query: str, engine: str, results: List[SearchResult]) -> bool:
        """將搜尋結果保存到快取中。"""
        if not self.cache_enabled or not results:
            return False
            
        cache_key = f"{engine}_{query}".replace(" ", "_").replace("/", "_").replace(".", "_")
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
        
        try:
            data = [result.to_dict() for result in results]
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            return True
        except Exception as e:
            logger.warning(f"保存 {engine} 的 {query} 快取時出錯: {e}")
            return False
    
    async def search(self, query: str, engines: Optional[List[str]] = None, force_refresh: bool = False) -> List[SearchResult]:
        """
        使用多個引擎搜尋查詢。
        
        參數:
            query: 要搜尋的查詢
            engines: 要使用的引擎列表（google, duckduckgo, bing, searxng 等）
            force_refresh: 是否忽略快取並強制進行新搜尋
        
        返回:
            搜尋結果列表
        """
        if engines is None:
            engines = ["google"]

        if isinstance(engines, str):
            engines = [engines]
        
        # 使用集合確保引擎名稱唯一（不區分大小寫）
        unique_engines = set(engine.lower() for engine in engines)

        tasks = []
        for engine in unique_engines:
            # 跳過不支持的引擎
            if engine not in ["google", "duckduckgo", "bing", "wikipedia", "searxng"]:
                logger.warning(f"未知的搜尋引擎: {engine}")
                continue
            
            # 記錄搜尋引擎和查詢
            logger.info(f"正在使用 {engine} 搜尋: {query}")  # 日誌寫入位置
            print(f"正在使用 {engine} 搜尋: {query}")  # 印出查詢
            
            # 使用適當的引擎方法執行搜尋
            if engine == "google":
                tasks.append(self._search_with_retry(self._search_google, query))
            elif engine == "duckduckgo":
                tasks.append(self._search_with_retry(self._search_duckduckgo, query))
            elif engine == "bing":
                tasks.append(self._search_with_retry(self._search_bing, query))
            elif engine == "wikipedia":
                tasks.append(self._search_with_retry(self._search_wikipedia, query))
            elif engine == "searxng":  # 新增 SearXNG 的條件分支
                tasks.append(self._search_with_retry(self._search_searxng, query))
        
        # 同時運行所有任務
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 扁平化結果並過濾掉異常
        all_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"搜尋過程中出錯: {result}")  # 日誌寫入位置
            else:
                all_results.extend(result)

        unique_urls = set()
        unique_results = []
        
        for result in all_results:
            if result.url not in unique_urls:
                unique_urls.add(result.url)
                unique_results.append(result)
                
        # 隨機打亂結果以混合引擎
        random.shuffle(unique_results)
        
        # 限制結果數量到 max_results
        return unique_results[:self.max_results]
    
    async def _search_with_retry(self, search_function, query: str, max_retries: int = 2) -> List[SearchResult]:
        """為搜尋函數添加重試邏輯的包裝器。"""
        retries = 0
        engine_name = search_function.__name__.replace("_search_", "")
        
        while retries <= max_retries:
            try:
                if retries > 0:
                    delay = random.uniform(1.0, 3.0) * retries
                    await asyncio.sleep(delay)

                semaphore = await self._get_semaphore()
                
                # 獲取信號量以限制並發搜尋
                async with semaphore:
                    await asyncio.sleep(random.uniform(0.1, 0.5))
                    
                    # 執行搜尋
                    results = await search_function(query)
                    
                    # 快取成功的結果
                    if results:
                        await self._save_to_cache(query, engine_name, results)
                        
                    return results
                    
            except Exception as e:
                logger.warning(f"第 {retries + 1} 次嘗試 {engine_name} 搜尋失敗: {e}")  # 日誌寫入位置
                retries += 1
                if retries > max_retries:
                    logger.error(f"所有 {max_retries + 1} 次嘗試 {engine_name} 搜尋失敗: {e}")  # 日誌寫入位置
                    return []
    
    async def _search_google(self, query: str) -> List[SearchResult]:
        """
        在 Google 上搜尋查詢。
        
        參數:
            query: 要搜尋的查詢
            
        返回:
            搜尋結果列表
        """
        try:
            # 使用 googlesearch-python 庫
            results = []
            google_results = list(google_search(query, num_results=self.max_results))
            for j in google_results:
                result = SearchResult(
                    url=j,
                    title=j,  # 我們無法從這個庫獲取標題
                    snippet="",  # 我們無法從這個庫獲取摘要
                    source="Google"
                )
                results.append(result)
            
            # 嘗試獲取標題和摘要
            if results:
                await self._enrich_google_results(results, query)
            
            return results
        except Exception as e:
            logger.error(f"在 Google 搜尋過程中出錯: {e}")  # 日誌寫入位置
            raise  # 重新引發以便重試機制
    
    async def _enrich_google_results(self, results: List[SearchResult], query: str) -> None:
        """
        用標題和摘要豐富 Google 搜尋結果。
        
        參數:
            results: 要豐富的搜尋結果列表
            query: 原始查詢
        """
        try:
            timeout = aiohttp.ClientTimeout(total=15)  # 15 秒超時
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"https://www.google.com/search?q={quote_plus(query)}"
                headers = {"User-Agent": self.user_agent}
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Google 搜尋返回狀態碼 {response.status}")  # 日誌寫入位置
                        return

                    html = await response.text()
                    soup = BeautifulSoup(html, features="html.parser")

                    search_divs = soup.find_all("div", class_="g")

                    for i, div in enumerate(search_divs):
                        if i >= len(results):
                            break

                        title_elem = div.find("h3")
                        if title_elem:
                            results[i].title = title_elem.text.strip()

                        snippet_elem = div.find("div", class_="VwiC3b")
                        if snippet_elem:
                            results[i].snippet = snippet_elem.text.strip()
                            
        except asyncio.TimeoutError:
            logger.warning("在豐富 Google 結果時超時")  # 日誌寫入位置
        except Exception as e:
            logger.error(f"豐富 Google 結果時出錯: {e}")  # 日誌寫入位置
            # 我們不會在這裡引發異常，因為這是輔助信息
    
    async def _search_duckduckgo(self, query: str) -> List[SearchResult]:
        """
        在 DuckDuckGo 上搜尋查詢。
        
        參數:
            query: 要搜尋的查詢
            
        返回:
            搜尋結果列表
        """
        try:
            timeout = aiohttp.ClientTimeout(total=15)  # 15 秒超時
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                headers = {"User-Agent": self.user_agent}
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"DuckDuckGo 搜尋返回狀態碼 {response.status}")  # 日誌寫入位置
                        raise ValueError(f"DuckDuckGo 搜尋返回狀態碼 {response.status}")

                    html = await response.text()
                    soup = BeautifulSoup(html, features="html.parser")

                    results = []
                    for result in soup.find_all("div", class_="result"):
                        title_elem = result.find("a", class_="result__a")
                        if not title_elem:
                            continue
                        
                        title = title_elem.text.strip()
                        url = title_elem.get("href", "")
                        if not url:
                            continue

                        if url.startswith("/"):
                            url = "https://duckduckgo.com" + url

                        snippet_elem = result.find("a", class_="result__snippet")
                        snippet = snippet_elem.text.strip() if snippet_elem else ""

                        result = SearchResult(
                            url=url,
                            title=title,
                            snippet=snippet,
                            source="DuckDuckGo"
                        )
                        results.append(result)
                        
                        # 限制結果數量到 max_results
                        if len(results) >= self.max_results:
                            break
                    
                    return results
                    
        except asyncio.TimeoutError:
            logger.warning(f"在 DuckDuckGo 搜尋查詢時超時: {query}")  # 日誌寫入位置
            raise
        except Exception as e:
            logger.error(f"在 DuckDuckGo 搜尋過程中出錯: {e}")  # 日誌寫入位置
            raise  # 重新引發以便重試機制
    
    async def _search_bing(self, query: str) -> List[SearchResult]:
        """
        在 Bing 上搜尋查詢。
        
        參數:
            query: 要搜尋的查詢
            
        返回:
            搜尋結果列表
        """
        try:
            timeout = aiohttp.ClientTimeout(total=15)  # 15 秒超時
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"https://www.bing.com/search?q={quote_plus(query)}"
                headers = {"User-Agent": self.user_agent}
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Bing 搜尋返回狀態碼 {response.status}")  # 日誌寫入位置
                        raise ValueError(f"Bing 搜尋返回狀態碼 {response.status}")

                    html = await response.text()
                    soup = BeautifulSoup(html, features="html.parser")

                    results = []
                    for result in soup.find_all("li", class_="b_algo"):
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

                        snippet_elem = result.find("div", class_="b_caption")
                        snippet = ""
                        if snippet_elem:
                            p_elem = snippet_elem.find("p")
                            if p_elem:
                                snippet = p_elem.text.strip()

                        result = SearchResult(
                            url=url,
                            title=title,
                            snippet=snippet,
                            source="Bing"
                        )
                        results.append(result)
                        
                        # 限制結果數量到 max_results
                        if len(results) >= self.max_results:
                            break
                    
                    return results
                    
        except asyncio.TimeoutError:
            logger.warning(f"在 Bing 搜尋查詢時超時: {query}")  # 日誌寫入位置
            raise  
        except Exception as e:
            logger.error(f"在 Bing 搜尋過程中出錯: {e}")  # 日誌寫入位置
            raise  # 重新引發以便重試機制
    
    async def _search_wikipedia(self, query: str) -> List[SearchResult]:
        """
        在 Wikipedia 上搜尋查詢。
        
        參數:
            query: 要搜尋的查詢
            
        返回:
            搜尋結果列表
        """
        try:
            timeout = aiohttp.ClientTimeout(total=15)  # 15 秒超時
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(query)}&limit={self.max_results}&namespace=0&format=json"
                headers = {"User-Agent": self.user_agent}
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Wikipedia 搜尋返回狀態碼 {response.status}")  # 日誌寫入位置
                        raise ValueError(f"Wikipedia 搜尋返回狀態碼 {response.status}")

                    data = await response.json()

                    results = []
                    for i in range(len(data[1])):
                        title = data[1][i]
                        snippet = data[2][i]
                        url = data[3][i]

                        result = SearchResult(
                            url=url,
                            title=title,
                            snippet=snippet,
                            source="Wikipedia"
                        )
                        results.append(result)
                    
                    return results
                    
        except asyncio.TimeoutError:
            logger.warning(f"在 Wikipedia 搜尋查詢時超時: {query}")  # 日誌寫入位置
            raise
        except Exception as e:
            logger.error(f"在 Wikipedia 搜尋過程中出錯: {e}")  # 日誌寫入位置
            raise  # 重新引發以便重試機制

    async def _search_searxng(self, query: str) -> List[SearchResult]:
        """
        使用 SearXNG 實例進行搜尋。
        
        參數:
            query: 要搜尋的查詢
            
        返回:
            搜尋結果列表
        """
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 使用公開的 SearXNG 實例或自架的實例
                searxng_url = "https://searx.be"  # 或其他 SearXNG 實例
                url = f"{searxng_url}/search?q={quote_plus(query)}&format=json"
                headers = {"User-Agent": self.user_agent}
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"SearXNG 搜尋返回狀態碼 {response.status}")  # 日誌寫入位置
                        raise ValueError(f"SearXNG 搜尋返回狀態碼 {response.status}")

                    data = await response.json()
                    results = []
                    
                    for result in data.get("results", [])[:self.max_results]:
                        search_result = SearchResult(
                            url=result.get("url", ""),
                            title=result.get("title", ""),
                            snippet=result.get("content", ""),
                            source="SearXNG"
                        )
                        results.append(search_result)
                    
                    return results
                    
        except asyncio.TimeoutError:
            logger.warning(f"在 SearXNG 搜尋查詢時超時: {query}")  # 日誌寫入位置
            raise
        except Exception as e:
            logger.error(f"在 SearXNG 搜尋過程中出錯: {e}")  # 日誌寫入位置
            raise

    def search_sync(self, query: str, engines: Optional[List[str]] = None, force_refresh: bool = False) -> List[SearchResult]:
        """
        同步版本的搜尋。
        
        參數:
            query: 要搜尋的查詢
            engines: 要使用的引擎列表
            force_refresh: 是否忽略快取並強制進行新搜尋
        
        返回:
            搜尋結果列表
        """
        return asyncio.run(self.search(query, engines, force_refresh))
    
    async def _get_semaphore(self) -> asyncio.Semaphore:
        """
        獲取或創建當前事件循環的信號量。
        
        這確保每個線程都有自己的信號量，綁定到正確的事件循環。
        """
        try:
            loop = asyncio.get_event_loop()
            loop_id = id(loop)
            
            # 如果我們已經有這個循環的信號量，則返回它
            if loop_id in self._semaphores:
                return self._semaphores[loop_id]
            
            # 否則，創建一個新的
            async with self._semaphore_lock:
                # 雙重檢查是否在我們等待時另一個任務已經創建了它
                if loop_id in self._semaphores:
                    return self._semaphores[loop_id]

                semaphore = asyncio.Semaphore(5)  # 限制為 5 個並發請求
                self._semaphores[loop_id] = semaphore
                return semaphore
                
        except RuntimeError:
            # 如果我們無法獲取事件循環，則創建一個新的並為其創建信號量
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            semaphore = asyncio.Semaphore(5)
            
            loop_id = id(loop)
            self._semaphores[loop_id] = semaphore
            return semaphore
    
    @lru_cache(maxsize=128)
    def _get_formatted_query(self, query: str, engine: str) -> str:
        """創建一個適合快取的格式化查詢字串。"""
        return f"{engine.lower()}:{query.lower()}"
