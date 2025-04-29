Shandu項目概述

Shandu是一個先進的AI研究系統，專為綜合知識合成而設計。根據代碼庫中的信息，Shandu是一個基於LLM（大型語言模型）的智能研究系統，能夠自動化完成從初始查詢到深入內容分析和報告生成的全面研究過程。

主要功能
Shandu系統具有以下主要功能：

基於狀態的工作流：利用LangGraph實現結構化、逐步的研究過程，具有明確的狀態轉換 README.md:82
迭代深度探索：通過動態深度和廣度遞歸探索主題，適應發現的信息 README.md:83
多源信息合成：分析來自搜索引擎、網頁內容和結構化知識庫的數據 README.md:84
增強型網頁抓取：具有動態JS渲染、內容提取和道德抓取實踐 README.md:85
智能源評估：自動評估源可信度、相關性和信息價值 README.md:86
內容分析管道：使用高級NLP提取關鍵信息、識別模式並綜合發現 README.md:87
全面報告生成：創建詳細、結構良好的報告，具有適當的引用和主題組織 README.md:88
研究工作流程
Shandu實現了一個複雜的多階段研究流程：

查詢澄清：交互式問題以瞭解研究需求 README.md:183
研究規劃：為全面主題覆蓋進行戰略規劃 README.md:184
迭代探索：
基於知識空白的智能查詢生成
具有並行執行的多引擎搜索
搜索結果的相關性過濾
具有內容提取的智能網頁抓取
源可信度評估
信息分析和綜合
對發現的反思以識別空白 README.md:185-192
報告生成：
主題提取和組織
多步報告增強
引用格式化和管理
全面覆蓋的章節擴展 README.md:193-197
系統架構
研究系統採用模塊化、狀態驅動的架構來有效管理研究工作流程。其核心是一個協調不同研究狀態之間轉換的有向圖實現。系統包括以下關鍵組件：

ResearchGraph：主要協調器，使用LangGraph的基於狀態的架構定義研究工作流程，管理不同研究階段之間的轉換。
ResearchAgent：執行特定研究任務，包括搜索、內容分析和知識提取，與AISearcher和WebScraper等外部系統接口。
AgentState：維護研究過程狀態的數據結構，包括累積知識、搜索結果和進度跟蹤。
研究節點：處理研究過程特定階段的專門組件：
初始化：設置研究上下文
反思：分析當前知識以識別空白
生成查詢：創建有針對性的搜索查詢
搜索：從多個來源檢索信息
源選擇：識別最相關的來源
引用：管理來源的適當歸屬
報告生成：創建最終研究輸出


使用方法
Shandu可以通过命令行界面或Python API使用：

命令行界面：

# 配置API设置（支持各种LLM提供商）  
shandu configure  
  
# 运行全面研究  
shandu research "您的研究查询" --depth 2 --breadth 4 --output report.md  
  
# 快速AI驱动搜索与网页抓取  
shandu aisearch "谁是美国现任总统？" --detailed  
  
# 基本多引擎搜索  
shandu search "您的搜索查询"
README.md:107-119

Python API：

from shandu.agents import ResearchGraph  
from langchain_openai import ChatOpenAI  
  
# 如果需要，使用自定义LLM初始化  
llm = ChatOpenAI(model="gpt-4")  
  
# 初始化研究图  
researcher = ResearchGraph(  
    llm=llm,  
    temperature=0.5  
)  
  
# 执行深度研究  
results = researcher.research_sync(  
    query="您的研究查询",  
    depth=3,       # 递归研究的深度  
    breadth=4,     # 要探索的并行查询数量  
    detail_level="high"  
)  
  
# 打印或保存结果  
print(results.to_markdown())
README.md:154-177

注意

Shandu是一个复杂的AI研究系统，它使用LangGraph的状态工作流来进行深入研究。系统通过迭代探索、多源信息合成和全面报告生成来提供详细的研究结果。根据README文件中的说明，这个项目是作者深入研究LangChain和LangGraph的一个项目，并且正在寻找贡献者。

Wiki pages you might want to explore:

Research Workflow (jolovicdev/shandu)
Research System (jolovicdev/shandu)

