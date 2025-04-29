# WebScraper 概述

WebScraper 是 Shandu 系統中負責從網頁提取內容的專門組件，它提供了強大的網頁抓取功能，包括靜態和動態頁面的處理、智能緩存和域名可靠性追踪 [scraper.py:114-115](#)。

## 主要特點

1. **靜態和動態頁面處理**  
   WebScraper 支持兩種抓取模式：
   - 靜態頁面抓取：使用 `WebBaseLoader` 快速抓取基本 HTML 內容
   - 動態頁面抓取：使用 `Playwright` 渲染 JavaScript，適用於現代網站 [scraper.py:283-287](#)
   
2. **智能緩存系統**  
   為了提高性能並減少重複請求，WebScraper 實現了基於文件的緩存系統：[scraper.py:29-39](#)  
   - 緩存檢查和保存的實現：[scraper.py:146-150](#), [scraper.py:183-187](#)

3. **域名可靠性追踪**  
   WebScraper 使用 `DomainReliability` 類來追踪不同域名的性能指標，並根據歷史表現調整超時設置：[scraper.py:42-48](#)  
   這使系統能夠自適應地處理不同網站的響應特性：[scraper.py:84-87](#)

4. **並發控制**  
   WebScraper 使用信號量來限制並發請求的數量，避免過度請求外部服務：[scraper.py:223-226](#)

5. **內容提取和處理**  
   WebScraper 不僅抓取原始 HTML，還能智能提取主要內容，過濾掉導航欄、頁腳等噪音元素：[scraper.py:515-520](#)  
   內容提取的實現非常全面，包括：
   - 識別主要內容容器
   - 移除導航、頁眉、頁腳等噪音
   - 規範化空白和格式
   - 移除重複內容 [scraper.py:527-533](#)

## 數據結構

### ScrapedContent

`ScrapedContent` 是存儲抓取結果的數據類，包含 URL、標題、文本內容、HTML 和元數據等信息：[scraper.py:92-106](#)

## 主要方法

1. **scrape_url**  
   `scrape_url` 方法是抓取單個 URL 的核心功能：[scraper.py:212-223](#)  
   這個方法的工作流程：
   - 檢查緩存
   - 如果沒有緩存結果，根據 `dynamic` 參數決定使用 `Playwright` 還是 `WebBaseLoader`
   - 提取和處理內容
   - 更新域名可靠性指標
   - 保存到緩存
   - 返回 `ScrapedContent` 對象

2. **scrape_urls**  
   `scrape_urls` 方法支持批量並行抓取多個 URL：[scraper.py:598-609](#)  
   這個方法的特點：
   - 過濾重複 URL
   - 並行執行抓取任務
   - 處理超時和錯誤
   - 保持結果順序與輸入 URL 一致 [scraper.py:622-636](#)

## 錯誤處理和重試機制

WebScraper 包含全面的錯誤處理和重試機制：
- 動態渲染失敗時的回退：如果 `Playwright` 渲染失敗，會回退到 `WebBaseLoader` [scraper.py:350-355](#)
- 超時處理：根據域名歷史性能自適應調整超時設置 [scraper.py:263-268](#)
- 批量抓取中的錯誤處理：單個 URL 失敗不會影響整體批量抓取 [scraper.py:632-635](#)

## 與研究系統的集成

WebScraper 與 Shandu 研究系統的其他組件緊密集成，特別是與 `AISearcher` 和 `search_node`：[ai_search.py:93-95](#)  
在搜索節點中的使用：[search.py:127-137](#)

## 配置選項

WebScraper 提供了多種配置選項，可以在初始化時設置：[scraper.py:117-135](#)  
主要配置參數包括：
- `proxy`：可選的代理 URL
- `timeout`：請求超時時間（秒）
- `max_concurrent`：最大並發抓取操作數
- `cache_enabled`：是否啟用緩存
- `cache_ttl`：緩存生存時間（秒）

## 總結

WebScraper 是 Shandu 研究系統中的核心內容抓取組件，提供了強大的網頁抓取功能，包括：
- 靜態和動態頁面處理
- 智能緩存系統
- 域名可靠性追踪
- 並發控制
- 智能內容提取  

這些功能使 Shandu 系統能夠高效、可靠地從網頁獲取研究所需的信息，為生成全面、準確的研究報告提供數據支持。
