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

