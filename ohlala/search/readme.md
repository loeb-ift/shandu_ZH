# Shandu 系統中的搜索功能

Shandu 系統中用於信息檢索的核心組件包括 `search` 和 `aisearch` 功能，這兩個功能分別實現在不同的文件中，但它們緊密相關並共同支持系統的研究能力。

## 1. 基本搜索功能 (search)

Shandu 的基本搜索功能主要由 `UnifiedSearcher` 類實現，位於 `shandu/search/search.py` 文件中。這個類提供了統一的搜索接口，可以同時使用多個搜索引擎。

### UnifiedSearcher 類的主要特點

- **多引擎支持**：可以同時使用 Google、DuckDuckGo、Bing 和 Wikipedia 等多個搜索引擎 [search.py:60-61](#)
- **並行搜索**：使用 `asyncio` 實現並行搜索，提高效率 [search.py:140-143](#)
- **結果緩存**：實現了基於文件的緩存系統，避免重複搜索 [search.py:88-91](#)
- **錯誤處理和重試**：包含完善的錯誤處理和重試機制 [search.py:211-215](#)

### 搜索過程

1. 接收查詢和指定的搜索引擎
2. 檢查緩存中是否有結果
3. 如果沒有緩存結果，則並行調用各個搜索引擎
4. 合併、去重並返回搜索結果

例如，DuckDuckGo 搜索的實現：[search.py:323-332](#)

### 在研究流程中的使用

在 Shandu 的研究流程中，`search_node` 使用 `UnifiedSearcher` 來執行搜索：[search.py:71-76](#)

## 2. AI 增強搜索功能 (aisearch)

Shandu 的 AI 增強搜索功能由 `AISearcher` 類實現，位於 `shandu/search/ai_search.py` 文件中。這個類在基本搜索的基礎上增加了 AI 分析和內容抓取功能。

### AISearcher 類的主要特點

- **基於 LLM 的分析**：使用大型語言模型分析和總結搜索結果 [ai_search.py:68-73](#)
- **內容抓取**：集成了 `WebScraper` 來抓取網頁內容，獲取更詳細的信息 [ai_search.py:163-168](#)
- **引用管理**：與 `CitationManager` 集成，跟踪來源和提取的信息 [ai_search.py:189-196](#)
- **結構化輸出**：返回包含摘要和來源信息的結構化結果 [ai_search.py:252-258](#)

### 搜索過程

1. 接收查詢和搜索選項
2. 使用 `DuckDuckGo` 工具或 `UnifiedSearcher` 獲取初始結果
3. 如果啟用了抓取功能，則抓取相關 URL 的內容
4. 使用 LLM 分析和總結結果
5. 返回包含摘要和來源的 `AISearchResult` 對象

### 在命令行界面中的使用

Shandu 的命令行界面提供了直接使用 `aisearch` 功能的方法：[README.md:114-115](#)

## 3. 兩者的比較和關係

### 功能比較

| 功能              | UnifiedSearcher (search) | AISearcher (aisearch)   |
|-------------------|--------------------------|--------------------------|
| 多引擎支持        | ✓                        | ✓ (通過 UnifiedSearcher) |
| 結果緩存          | ✓                        | ✓ (通過 UnifiedSearcher) |
| 內容抓取          | ✗                        | ✓                        |
| AI 分析           | ✗                        | ✓                        |
| 引用管理          | ✗                        | ✓                        |
| 結構化輸出        | 基本                     | 豐富                     |

### 关系

`AISearcher` 實際上是對 `UnifiedSearcher` 的增強，它使用 `UnifiedSearcher` 作為基礎搜索引擎，然後添加了 AI 分析、內容抓取和引用管理等功能：[ai_search.py:93-95](#)

在研究流程中，`search_node` 使用 `UnifiedSearcher` 進行搜索，然後自己處理內容抓取和分析。而在直接使用 `aisearch` 命令時，則使用 `AISearcher` 一次性完成所有這些步驟。

## 4. 實際使用示例

### 基本搜索 (search)



UnifiedSearcher 概述

UnifiedSearcher 是一個統一的搜索引擎類，能夠同時使用多個搜索引擎，並具有改進的並行處理和緩存功能。這個類位於 shandu/search/search.py 文件中。 search.py:60-61

主要特點

1. 多引擎支持
UnifiedSearcher 支持同時使用多個搜索引擎，包括 Google、DuckDuckGo、Bing 和 Wikipedia。這使得系統能夠從多個來源獲取信息，提高搜索結果的全面性和多樣性。

2. 並行搜索
該類使用 asyncio 實現並行搜索，同時向多個搜索引擎發送請求，大大提高了搜索效率。搜索方法是異步的，允許同時處理多個搜索請求： search.py:140-143

3. 結果緩存
UnifiedSearcher 實現了基於文件的緩存系統，避免重複搜索相同的查詢，提高響應速度並減少對外部搜索引擎的請求： search.py:88-91

4. 錯誤處理和重試機制
該類包含完善的錯誤處理和重試機制，確保在搜索過程中遇到臨時問題時能夠自動重試： search.py:211-215

初始化和配置

UnifiedSearcher 在初始化時可以設置多個參數，包括最大結果數、是否啟用緩存以及緩存的生存時間：

def __init__(self, max_results: int = 10, cache_enabled: bool = CACHE_ENABLED, cache_ttl: int = CACHE_TTL):
這些參數允許用戶根據自己的需求自定義搜索行為。

搜索過程

UnifiedSearcher 的搜索過程如下：

接收查詢和指定的搜索引擎
檢查緩存中是否有結果
如果沒有緩存結果，則並行調用各個搜索引擎
合併、去重並返回搜索結果
例如，DuckDuckGo 搜索的實現： search.py:323-332

在研究流程中的使用

在 Shandu 的研究流程中，search_node 使用 UnifiedSearcher 來執行搜索： search.py:71-76

這段代碼展示了如何在研究過程中使用多個搜索引擎（Google、DuckDuckGo 和 Wikipedia）來獲取更全面的搜索結果。

與 AISearcher 的關係

UnifiedSearcher 是 AISearcher 的基礎組件。AISearcher 使用 UnifiedSearcher 作為基礎搜索引擎，然後添加了 AI 分析、內容抓取和引用管理等高級功能： ai_search.py:93-95

搜索引擎實現

UnifiedSearcher 為每個支持的搜索引擎提供了專門的實現方法：

Google 搜索：使用 googlesearch-python 庫，並進行結果豐富化
DuckDuckGo 搜索：抓取 HTML 搜索結果頁面

Bing 搜索：抓取 HTML 搜索結果頁面
Wikipedia 搜索：使用 Wikipedia API 的 opensearch 操作
每個引擎實現都包括錯誤處理、重試、速率限制和超時管理。

緩存系統

UnifiedSearcher 實現了基於文件的緩存系統，以提高性能並減少重複搜索：

緩存條目以 JSON 文件形式存儲
每個緩存條目都有一個 TTL（生存時間）
可以禁用緩存或使用 force_refresh 參數繞過緩存
緩存鍵由查詢和引擎名稱生成
並發控制

UnifiedSearcher 使用信號量來限制並發請求的數量，避免過度請求外部服務：

semaphore = asyncio.Semaphore(5)  # 限制為 5 個並發請求
這確保了系統不會因為過多的並發請求而超出外部服務的限制或導致性能問題。

總結

UnifiedSearcher 是 Shandu 研究系統中的核心搜索組件，提供了統一的多引擎搜索接口，具有並行處理、緩存、錯誤處理和重試等功能。它為系統的信息檢索能力提供了堅實的基礎，並與 AISearcher 等高級組件集成，共同支持 Shandu 的研究功能。
