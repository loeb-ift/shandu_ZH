# Shandu: 高級研究系統架構

此目錄包含閃度深度研究系統的核心架構。我們的模塊化設計將不同功能分離，在保持代碼整潔、可測試的同時，實現未來的可擴展性。

## 📊 系統架構

閃度使用LangGraph和LangChain實現了一個複雜的基於狀態的工作流程，以創建一個強大、可擴展的研究系統：

```
shandu/
## 🔄 LangGraph研究工作流程

閃度的研究過程遵循一個複雜的基於狀態的工作流程：

1. **初始化**：定義研究查詢、參數，並創建研究計劃
2. **反思**：分析當前發現，識別知識差距
3. **生成查詢**：根據分析創建目標搜索查詢
4. **搜索**：執行搜索查詢並收集結果
5. **智能來源選擇**：過濾和優先排序最有價值的來源
6. **格式化引用**：為所有來源準備正確格式化的引用
7. **生成初始報告**：創建研究報告的初稿
8. **增強報告**：增加深度、細節和適當的結構
9. **擴展關鍵部分**：通過多步綜合進一步發展重要部分
10. **最終確定報告**：應用最終格式和質量檢查

## 🧠 高級技術特性

### 基於LangGraph的狀態研究

我們的LangGraph實現提供了幾個關鍵優勢：

- **清晰的狀態轉換**：每個研究階段都有明確的輸入和輸出
- **條件邏輯**：根據當前狀態動態確定下一個步驟
- **循環流程**：支持遞歸探索，直到達到深度條件
- **並行處理**：處理併發操作以提高效率
- **錯誤恢復能力**：即使個別步驟遇到問題，仍能繼續運行

### 增強的內容處理

閃度實現了複雜的內容處理：

- **內容相關性過濾**：使用人工智能確定內容是否與研究查詢相關
- **來源可靠性評估**：評估來源的可信度和權威性
- **主要內容提取**：識別和提取網頁的主要內容
- **內容分析管道**：多步分析以提取關鍵信息
- **主題識別**：自動發現和組織主題元素

### 高級報告生成

我們的多步報告生成過程確保高質量的輸出：

1. **主題提取**：識別所有研究中的關鍵主題
2. **初始報告生成**：創建一個結構化的初稿
3. **報告增強**：增加深度、引用和改進組織
4. **關鍵部分擴展**：進一步發展最重要的部分
5. **引用管理**：確保所有來源的正確歸屬
6. **最終清理**：移除殘留物並確保一致的格式

## 💻 API詳細信息

### ResearchGraph類

```python
class ResearchGraph:
    """
    使用LangGraph的基於狀態的研究工作流程。
    提供一個結構化的方法進行多階段的深度研究。
    """
    def __init__(
        self, 
        llm: Optional[ChatOpenAI] = None, 
        searcher: Optional[UnifiedSearcher] = None, 
        scraper: Optional[WebScraper] = None, 
        temperature: float = 0.5,
        date: Optional[str] = None
    )
    
    async def research(
        self, 
        query: str, 
        depth: int = 2, 
        breadth: int = 4, 
        progress_callback: Optional[Callable] = None,
        include_objective: bool = False,
        detail_level: str = "high" 
    ) -> ResearchResult
    
    def research_sync(
        self, 
        query: str, 
        depth: int = 2, 
        breadth: int = 4, 
        progress_callback: Optional[Callable] = None,
        include_objective: bool = False,
        detail_level: str = "high"
    ) -> ResearchResult
```

### AISearcher Class

```python
class AISearcher:
    """
    AI-powered search with content scraping for deeper insights.
    """
    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        searcher: Optional[UnifiedSearcher] = None,
        scraper: Optional[WebScraper] = None,
        max_results: int = 10,
        max_pages_to_scrape: int = 3
    )
    
    async def search(
        self, 
        query: str,
        engines: Optional[List[str]] = None,
        detailed: bool = False,
        enable_scraping: bool = True
    ) -> AISearchResult
```

# Shandu: 高級研究系統架構
## 🔌 整合點

Shandu 設計為易於整合：

- **CLI 介面**：直接使用的命令列工具
- **Python API**：乾淨、文檔完善的 API，可用於整合到其他應用程式中
- **可擴展組件**：易於添加新的搜索引擎、抓取器或處理步驟
- **自定義 LLM 支援**：可與任何 LangChain 相容的 LLM 一起使用
- **回調系統**：進度追蹤和事件鉤子

# Shandu: 高級研究系統架構
## 🔍 實作細節
### 提示工程

Shandu 使用精心設計的提示用於：

- 查詢澄清
- 研究規劃
- 內容分析
- 來源評估
- 報告生成
- 引用格式設定

### Async Processing

# Shandu: 高級研究系統架構
## 🔌 整合點
閃度設計為易於整合：

- CLI介面 ：直接使用的命令列工具
- Python API ：乾淨、文檔完善的API，可用於整合到其他應用程式中
- 可擴展組件 ：易於添加新的搜索引擎、抓取器或處理步驟
- 自定義LLM支援 ：可與任何LangChain相容的LLM一起使用
- 回調系統 ：進度追蹤和事件鉤子
# Shandu: 高級研究系統架構
## 🔍 實作細節
### 提示工程
閃度使用精心設計的提示用於：

- 查詢澄清
- 研究規劃
- 內容分析
- 來源評估
- 報告生成
- 引用格式設定
### 非同步處理
廣泛使用非同步/等待模式用於：

- 並行搜索執行
- 併發網頁爬蟲
- 高效的內容處理
- 響應式UI更新
### 緩存系統
多級緩存用於：

- 搜索結果
- 爬取的內容
- 內容分析
- LLM回覆
## 🔬 研究算法
我們的研究算法優化以下方面：

1. 廣度 ：探索多個相關的子主題
2. 深度 ：深入挖掘重要細節
3. 收斂 ：聚焦於最相關的信息
4. 覆蓋率 ：確保全面的主題探索
5. 來源質量 ：優先考慮可靠、權威的來源
6. 綜合 ：創建連貫、結構良好的報告
有關使用閃度的更多信息，請參閱主 README.md 文件。