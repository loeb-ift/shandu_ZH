"""
閃度研究系統的網頁爬蟲模塊。
提供與WebBaseLoader集成的網頁爬取功能。
"""
import os
import re
import asyncio
import time
import random
from typing import List, Dict, Any, Optional, Union, Set
from dataclasses import dataclass
import logging
from urllib.parse import urlparse
import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader
from pydantic import BaseModel, Field
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 嘗試從環境變量中獲取USER_AGENT，否則使用通用的USER_AGENT
USER_AGENT = os.environ.get('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

# 緩存設置
CACHE_ENABLED = True
CACHE_DIR = os.path.expanduser("~/.shandu/cache/scraper")
CACHE_TTL = 86400  # 24小時，以秒為單位

if CACHE_ENABLED and not os.path.exists(CACHE_DIR):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"無法創建緩存目錄: {e}")
        CACHE_ENABLED = False

# 域名可靠性追蹤
class DomainReliability:
    """追蹤域名的可靠性指標，以優化爬取過程。"""
    def __init__(self):
        self.domain_metrics: Dict[str, Dict[str, Any]] = {}
        self.DEFAULT_TIMEOUT = 10.0
        
    def get_timeout(self, url: str) -> float:
        """根據過往表現為域名獲取合適的超時時間。"""
        domain = urlparse(url).netloc
        if domain in self.domain_metrics:
            # 如果有特定域名的超時時間，則使用該時間
            return self.domain_metrics[domain].get("timeout", self.DEFAULT_TIMEOUT)
        return self.DEFAULT_TIMEOUT
        
    def update_metrics(self, url: str, success: bool, response_time: float, status_code: Optional[int] = None) -> None:
        """根據爬取結果更新域名的指標。"""
        domain = urlparse(url).netloc
        if domain not in self.domain_metrics:
            self.domain_metrics[domain] = {
                "success_count": 0,
                "fail_count": 0,
                "avg_response_time": 0,
                "timeout": self.DEFAULT_TIMEOUT,
                "status_codes": {}
            }
            
        metrics = self.domain_metrics[domain]

        if success:
            metrics["success_count"] += 1
        else:
            metrics["fail_count"] += 1

        if response_time > 0:
            total_requests = metrics["success_count"] + metrics["fail_count"]
            metrics["avg_response_time"] = (
                (metrics["avg_response_time"] * (total_requests - 1) + response_time) / total_requests
            )

        if status_code:
            metrics["status_codes"][str(status_code)] = metrics["status_codes"].get(str(status_code), 0) + 1
            
        # 根據響應時間調整超時時間
        if metrics["success_count"] >= 3:
            metrics["timeout"] = min(30.0, max(5.0, metrics["avg_response_time"] * 1.5))

# 全局域名可靠性追蹤器
domain_reliability = DomainReliability()

@dataclass
class ScrapedContent:
    """用於存儲從網頁爬取的內容的類。"""
    url: str
    title: str
    text: str
    html: str
    content_type: str
    metadata: Dict[str, Any]
    error: Optional[str] = None
    scrape_time: float = 0.0
    
    def is_successful(self) -> bool:
        """檢查爬取是否成功。"""
        return self.error is None and len(self.text) > 0
    
    def get_cache_key(self) -> str:
        """為此內容生成緩存鍵。"""
        domain = urlparse(self.url).netloc
        path = urlparse(self.url).path
        return f"{domain}{path}".replace("/", "_").replace(".", "_")

class WebScraper:
    """使用WebBaseLoader從網頁提取內容的網頁爬蟲。"""
    
    def __init__(self, proxy: Optional[str] = None, timeout: int = 10, max_concurrent: int = 5,
                 cache_enabled: bool = CACHE_ENABLED, cache_ttl: int = CACHE_TTL):
        """
        初始化網頁爬蟲。
        
        參數:
            proxy: 可選的代理URL，用於請求
            timeout: 請求的默認超時時間，以秒為單位
            max_concurrent: 最大並發爬取操作數
            cache_enabled: 是否對爬取的內容使用緩存
            cache_ttl: 緩存內容的存活時間，以秒為單位
        """
        self.proxy = proxy
        self.timeout = timeout
        self.max_concurrent = max(1, min(max_concurrent, 10))  # 限制在1到10之間
        self.user_agent = USER_AGENT
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self.in_progress_urls: Set[str] = set()  # 追蹤正在爬取的URL，以防止重複
        self._semaphores = {}  # 用於存儲每個事件循環的信號量的字典
        self._semaphore_lock = asyncio.Lock()  # 用於線程安全訪問信號量的鎖
        
        # 嘗試使用fake_useragent（如果可用）
        try:
            ua = UserAgent()
            self.user_agent = ua.random
        except Exception as e:
            logger.warning(f"無法生成隨機用戶代理: {e}。使用默認值。")
    
    async def _check_cache(self, url: str) -> Optional[ScrapedContent]:
        """檢查緩存中是否有可用的內容且未過期。"""
        if not self.cache_enabled:
            return None
            
        domain = urlparse(url).netloc
        path = urlparse(url).path
        cache_key = f"{domain}{path}".replace("/", "_").replace(".", "_")
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
        
        if not os.path.exists(cache_path):
            return None
            
        try:
            if time.time() - os.path.getmtime(cache_path) > self.cache_ttl:
                return None
                
            # 加載緩存內容
            import json
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return ScrapedContent(
                url=data["url"],
                title=data["title"],
                text=data["text"],
                html=data["html"],
                content_type=data["content_type"],
                metadata=data["metadata"],
                error=data.get("error"),
                scrape_time=data.get("scrape_time", 0.0)
            )
        except Exception as e:
            logger.warning(f"加載 {url} 的緩存時出錯: {e}")
            return None
    
    async def _save_to_cache(self, content: ScrapedContent) -> bool:
        """將爬取的內容保存到緩存中。"""
        if not self.cache_enabled or not content.is_successful():
            return False
            
        cache_key = content.get_cache_key()
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
        
        try:
            import json
            data = {
                "url": content.url,
                "title": content.title,
                "text": content.text,
                "html": content.html[:50000],  # 限制HTML大小，以避免緩存文件過大
                "content_type": content.content_type,
                "metadata": content.metadata,
                "error": content.error,
                "scrape_time": content.scrape_time or time.time()
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=None)
            return True
        except Exception as e:
            logger.warning(f"保存 {content.url} 的緩存時出錯: {e}")
            return False
    
    async def scrape_url(self, url: str, dynamic: bool = False, force_refresh: bool = False) -> ScrapedContent:
        """
        使用WebBaseLoader以智能超時和緩存從URL爬取內容。
        
        參數:
            url: 要爬取的URL
            dynamic: 是否使用動態渲染（用於JavaScript密集型網站）
            force_refresh: 是否忽略緩存並強制進行全新爬取
            
        返回:
            包含爬取內容的ScrapedContent對象
        """
        start_time = time.time()
        logger.info(f"正在爬取URL: {url}")

        if not url.startswith(('http://', 'https://')):
            return ScrapedContent(
                url=url,
                title="",
                text="",
                html="",
                content_type="",
                metadata={},
                error="無效的URL格式",
                scrape_time=start_time
            )

        if url in self.in_progress_urls:
            return ScrapedContent(
                url=url,
                title="",
                text="",
                html="",
                content_type="",
                metadata={},
                error="URL正在處理中",
                scrape_time=start_time
            )
            
        # 標記為正在處理
        self.in_progress_urls.add(url)
        
        try:
            if not force_refresh:
                cached_content = await self._check_cache(url)
                if cached_content:
                    logger.info(f"使用 {url} 的緩存內容")
                    self.in_progress_urls.remove(url)
                    return cached_content

            adaptive_timeout = domain_reliability.get_timeout(url)
            
            # 配置WebBaseLoader的適當設置
            requests_kwargs = {
                "headers": {"User-Agent": self.user_agent},
                "timeout": adaptive_timeout,
                "verify": True  # SSL驗證
            }
            
            if self.proxy:
                requests_kwargs["proxies"] = {
                    "http": self.proxy,
                    "https": self.proxy
                }

            semaphore = await self._get_semaphore()
            
            # 獲取信號量以限制並發性
            async with semaphore:
                # 如果請求動態渲染，則使用Playwright
                if dynamic:
                    try:
                        from playwright.async_api import async_playwright
                        
                        async with async_playwright() as p:
                            browser = await p.chromium.launch(headless=True)
                            page = await browser.new_page(user_agent=self.user_agent)

                            page.set_default_timeout(adaptive_timeout * 1000)
                            
                            # 帶超時處理的方式導航到URL
                            try:
                                await asyncio.wait_for(
                                    page.goto(url, wait_until="networkidle"),
                                    timeout=adaptive_timeout
                                )

                                html_content = await page.content()

                                title = await page.title()
                                
                                # 關閉瀏覽器
                                await browser.close()

                                soup = BeautifulSoup(html_content, "lxml")

                                metadata = self._extract_metadata(soup, url)

                                main_content = self._extract_main_content(soup)
                                
                                end_time = time.time()
                                scrape_time = end_time - start_time

                                domain_reliability.update_metrics(
                                    url=url, 
                                    success=True, 
                                    response_time=scrape_time, 
                                    status_code=200
                                )
                                
                                result = ScrapedContent(
                                    url=url,
                                    title=title,
                                    text=main_content,
                                    html=html_content,
                                    content_type="text/html",
                                    metadata=metadata,
                                    scrape_time=scrape_time
                                )
                                
                                # 緩存成功的結果
                                await self._save_to_cache(result)
                                
                                # 從正在處理的集合中移除
                                self.in_progress_urls.remove(url)
                                
                                return result
                                
                            except asyncio.TimeoutError:
                                await browser.close()
                                logger.warning(f"Playwright對 {url} 超時")

                                domain_reliability.update_metrics(
                                    url=url, 
                                    success=False, 
                                    response_time=adaptive_timeout
                                )
                                # 回退到WebBaseLoader
                                
                    except ImportError:
                        logger.warning("未安裝Playwright。回退到WebBaseLoader。")
                    except Exception as e:
                        logger.error(f"動態渲染期間出錯: {e}。回退到WebBaseLoader。")

                        domain_reliability.update_metrics(
                            url=url, 
                            success=False, 
                            response_time=time.time() - start_time
                        )
                
                # 使用WebBaseLoader進行爬取
                loader = WebBaseLoader(
                    web_path=url,
                    requests_kwargs=requests_kwargs,
                    bs_kwargs={},  # BeautifulSoup在內部已經獲取了features參數
                    raise_for_status=True,
                    continue_on_failure=False,
                    autoset_encoding=True,
                    trust_env=True
                )
                
                try:
                    # 使用WebBaseLoader加載文檔
                    documents = await asyncio.to_thread(loader.load)
                    
                    if not documents:
                        end_time = time.time()
                        scrape_time = end_time - start_time

                        domain_reliability.update_metrics(
                            url=url, 
                            success=False, 
                            response_time=scrape_time
                        )
                        
                        self.in_progress_urls.remove(url)
                        return ScrapedContent(
                            url=url,
                            title="",
                            text="",
                            html="",
                            content_type="",
                            metadata={},
                            error="未找到內容",
                            scrape_time=scrape_time
                        )

                    document = documents[0]

                    metadata = document.metadata

                    text_content = document.page_content

                    # 僅在文本非常長時進行分割，以減少處理開銷
                    if len(text_content) > 20000:
                        text_splitter = RecursiveCharacterTextSplitter(
                            chunk_size=10000,
                            chunk_overlap=200,
                            length_function=len,
                        )
                        chunks = text_splitter.split_text(text_content)
                        text_content = "\n\n".join(chunks[:5])  # 使用前5個塊以獲得更全面的覆蓋

                    text_content = re.sub(r'\n{3,}', '\n\n', text_content)
                    text_content = re.sub(r'\s{2,}', ' ', text_content)
                    
                    # 移除可能與Rich標記衝突的有問題的模式
                    # 這可以防止在控制檯中顯示此文本時出現問題
                    text_content = re.sub(r'\[\]', ' ', text_content)  # 空括號
                    text_content = re.sub(r'\[\/?[^\]]*\]?', ' ', text_content)  # 不完整/格式錯誤的標籤
                    text_content = re.sub(r'\[[^\]]*\]', ' ', text_content)  # 任何括號內的內容

                    html_content = ""
                    if hasattr(loader, "_html_content") and loader._html_content:
                        html_content = loader._html_content

                    title = metadata.get("title", "")
                    if not title and html_content:
                        soup = BeautifulSoup(html_content, "lxml")
                        title_tag = soup.find("title")
                        if title_tag:
                            title = title_tag.text.strip()

                    content_type = metadata.get("content-type", "text/html")
                    
                    end_time = time.time()
                    scrape_time = end_time - start_time

                    domain_reliability.update_metrics(
                        url=url, 
                        success=True, 
                        response_time=scrape_time,
                        status_code=metadata.get("status_code")
                    )
                    
                    result = ScrapedContent(
                        url=url,
                        title=title,
                        text=text_content,
                        html=html_content,
                        content_type=content_type,
                        metadata=metadata,
                        scrape_time=scrape_time
                    )
                    
                    # 緩存成功的結果
                    await self._save_to_cache(result)
                    
                    # 從正在處理的集合中移除
                    self.in_progress_urls.remove(url)
                    
                    return result
                    
                except Exception as e:
                    logger.error(f"使用WebBaseLoader時出錯: {e}")
                    raise  # 重新拋出以被外部try/except捕獲
            
        except Exception as e:
            end_time = time.time()
            scrape_time = end_time - start_time
            
            logger.error(f"爬取URL {url} 時出錯: {str(e)}")

            domain_reliability.update_metrics(
                url=url, 
                success=False, 
                response_time=scrape_time
            )
            
            # 從正在處理的集合中移除
            self.in_progress_urls.remove(url)
            
            return ScrapedContent(
                url=url,
                title="",
                text="",
                html="",
                content_type="",
                metadata={},
                error=str(e),
                scrape_time=scrape_time
            )
    
    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, str]:
        """從BeautifulSoup對象中提取元數據。"""
        metadata = {
            "url": url,
            "domain": urlparse(url).netloc
        }

        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.text.strip()

        for meta in soup.find_all("meta"):
            name = meta.get("name", meta.get("property", ""))
            content = meta.get("content", "")
            if name and content:
                metadata[name.lower()] = content
        
        return metadata
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """
        從BeautifulSoup對象中提取主要內容。
        
        此函數嘗試識別網頁的主要內容區域，並返回其文本內容，格式一致。
        """
        # 首先，嘗試移除常見的噪聲元素
        for noise_tag in soup.select('nav, header, footer, aside, .menu, .sidebar, .navigation, .ad, .advertisement, script, style, [role="banner"], [role="navigation"]'):
            if noise_tag:
                noise_tag.decompose()
                
        # 嘗試查找主要內容容器
        main_tags = soup.find_all(
            ["main", "article", "div", "section"], 
            class_=lambda c: c and any(x in str(c).lower() for x in [
                "content", "main", "article", "body", "entry", "post", "text"
            ])
        )
        
        content = ""
        if main_tags:
            # 使用最大的內容容器
            main_tag = max(main_tags, key=lambda tag: len(tag.get_text(strip=True)))
            content = main_tag.get_text(separator="\n", strip=True)
        else:
            # 如果未找到主要內容容器，則使用body
            body = soup.find("body")
            if body:
                content = body.get_text(separator="\n", strip=True)
            else:
                # 如果未找到body，則使用整個HTML
                content = soup.get_text(separator="\n", strip=True)
        
        # 對內容進行徹底清理
        # 移除重複的標題/頁腳
        content = re.sub(r'([^\n]+)(\n\1)+', r'\1', content)
        
        # 規範化空格
        content = re.sub(r'\n{3,}', '\n\n', content)  # 將3個或更多換行符替換為2個
        content = re.sub(r'\s{2,}', ' ', content)     # 將多個空格替換為1個
        
        # 移除可能是菜單項或噪聲的非常短的行
        content_lines = [line for line in content.split('\n') if len(line.strip()) > 3]
        content = '\n'.join(content_lines)
        
        return content.strip()
    
    async def _get_semaphore(self) -> asyncio.Semaphore:
        """
        獲取或創建當前事件循環的信號量。
        
        這確保每個線程都有自己的信號量，並綁定到正確的事件循環。
        """
        try:
            loop = asyncio.get_event_loop()
            loop_id = id(loop)
            
            # 如果已經有此循環的信號量，則返回它
            if loop_id in self._semaphores:
                return self._semaphores[loop_id]
            
            # 否則，創建一個新的信號量
            async with self._semaphore_lock:
                # 再次檢查在等待期間是否有其他任務已經創建了它
                if loop_id in self._semaphores:
                    return self._semaphores[loop_id]

                semaphore = asyncio.Semaphore(self.max_concurrent)
                self._semaphores[loop_id] = semaphore
                return semaphore
                
        except RuntimeError:
            # 如果無法獲取事件循環，則創建一個新的事件循環和信號量
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            loop_id = id(loop)
            self._semaphores[loop_id] = semaphore
            return semaphore
            
    async def scrape_urls(self, urls: List[str], dynamic: bool = False, force_refresh: bool = False) -> List[ScrapedContent]:
        """
        以改進的並行性和錯誤處理方式同時爬取多個URL。
        
        參數:
            urls: 要爬取的URL列表
            dynamic: 是否使用動態渲染
            force_refresh: 是否忽略緩存並強制進行全新爬取
            
        返回:
            ScrapedContent對象列表
        """
        if not urls:
            return []
            
        # 過濾重複項，同時保留順序
        unique_urls = []
        seen = set()
        for url in urls:
            if url not in seen:
                unique_urls.append(url)
                seen.add(url)
                
        # 使用asyncio.gather和信號量進行並發控制
        # 信號量在scrape_url內部處理，因此這裡不需要應用它
        tasks = [self.scrape_url(url, dynamic, force_refresh) for url in unique_urls]
        
        try:
            # 使用as_completed模式更好地處理單個超時
            results = []
            for task in asyncio.as_completed(tasks, timeout=60):  # 總體超時
                try:
                    result = await task
                    results.append(result)
                except asyncio.TimeoutError:
                    logger.warning(f"批量爬取期間任務超時")
                except Exception as e:
                    logger.error(f"爬取任務出錯: {e}")
                    
            # 將結果排序回與輸入順序匹配
            result_map = {r.url: r for r in results if hasattr(r, 'url')}
            ordered_results = [result_map.get(url, None) for url in unique_urls]
            
            # 將None值替換為錯誤對象
            for i, result in enumerate(ordered_results):
                if result is None:
                    ordered_results[i] = ScrapedContent(
                        url=unique_urls[i],
                        title="",
                        text="",
                        html="",
                        content_type="",
                        metadata={},
                        error="未能完成爬取",
                        scrape_time=time.time()
                    )
            
            return ordered_results
            
        except asyncio.TimeoutError:
            logger.error("批量爬取期間超過了總體超時時間")

            completed_results = [task.result() if task.done() and not task.exception() else None for task in tasks]
            
            # 將None值替換為錯誤對象
            for i, result in enumerate(completed_results):
                if result is None:
                    completed_results[i] = ScrapedContent(
                        url=unique_urls[i] if i < len(unique_urls) else "unknown",
                        title="",
                        text="",
                        html="",
                        content_type="",
                        metadata={},
                        error="批量爬取期間超時",
                        scrape_time=time.time()
                    )
            
            return completed_results
        except Exception as e:
            logger.error(f"批量爬取期間出現意外錯誤: {e}")
            return [ScrapedContent(
                url=url,
                title="",
                text="",
                html="",
                content_type="",
                metadata={},
                error=f"批量爬取錯誤: {str(e)}",
                scrape_time=time.time()
            ) for url in unique_urls]

# 爬取的結構化輸出模型
class ScrapingResult(BaseModel):
    """爬取結果的結構化輸出。"""
    url: str = Field(description="被爬取頁面的URL")
    title: str = Field(description="頁面的標題")
    content: str = Field(description="從頁面提取的內容")
    success: bool = Field(description="爬取是否成功")
    error: Optional[str] = Field(description="如果爬取失敗，則顯示錯誤消息", default=None)