# agents/graph/ 目錄概述

`agents/graph/` 目錄包含了用於構建 LangGraph 狀態圖的代碼，這個狀態圖定義了 Shandu 研究系統的工作流程。根據系統架構，這個目錄的主要功能是協調不同的研究節點，形成一個完整的研究流程。

## 核心組件：build_graph 函數

根據系統架構文檔，`agents/graph/builder.py` 文件中的 `build_graph` 函數是這個目錄的核心組件。這個函數負責將各個研究節點連接起來，形成一個完整的工作流程圖：

這個函數接收多個節點函數作為參數，包括初始化節點、反思節點、查詢生成節點等，然後將它們添加到 `StateGraph` 中，並定義節點之間的連接關係。

## 工作流程圖的結構

根據 `build_graph` 函數的實現，Shandu 研究系統的工作流程圖具有以下結構：

- **入口點**: 初始化節點 (initialize)
- **主要研究循環**:
  - 反思節點 (reflect)
  - 生成查詢節點 (generate_queries)
  - 搜索節點 (search)
- **條件轉換**: 搜索節點完成後，根據 `should_continue` 函數的結果決定是繼續研究還是進入報告生成階段
- **報告生成階段**:
  - 智能來源選擇節點 (smart_source_selection)
  - 引用格式化節點 (format_citations)
  - 初始報告生成節點 (generate_initial_report)
  - 報告增強節點 (enhance_report)
  - 關鍵部分擴展節點 (expand_key_sections)
  - 最終報告節點 (report)
- **結束點**: 最終報告節點 (report)

## 狀態管理

工作流程圖使用 `AgentState` 類型來維護和傳遞狀態。每個節點接收當前狀態，處理它，然後返回更新後的狀態給下一個節點。這種基於狀態的設計使得整個研究過程能夠保持連貫性，並且能夠在節點之間傳遞信息。

## 條件轉換

工作流程圖中的一個關鍵特性是條件轉換，特別是從搜索節點到後續節點的轉換。這是通過 `should_continue` 函數實現的，該函數根據當前的迭代次數和深度參數決定是繼續研究還是進入報告生成階段。

## 與其他組件的集成

`agents/graph/` 目錄中的代碼與 Shandu 系統的其他組件緊密集成：

- **與 nodes 目錄的集成**: 工作流程圖使用 nodes 目錄中定義的各個節點函數。
- **與 ResearchGraph 類的集成**: `ResearchGraph` 類在初始化時會調用 `_build_graph` 方法，該方法使用 `build_graph` 函數來構建工作流程圖 [langgraph_agent.py:68-94](#)。
- **與 CLI 的集成**: CLI 通過 `ResearchGraph` 類使用工作流程圖來執行研究 [cli.py:363-404](#)。

## 工作流程圖的執行

當用戶通過 CLI 啟動研究過程時，系統會創建 `ResearchGraph` 實例，然後調用其 `research_sync` 方法執行研究。這個方法會使用工作流程圖來協調各個節點的執行，從初始化節點開始，然後根據條件和狀態轉換到後續節點。

整個執行過程是通過 LangGraph 的 `StateGraph` 類自動管理的，該類負責根據定義的邊和條件在節點之間傳遞狀態。

## 總結

`agents/graph/` 目錄是 Shandu 研究系統的核心組件，負責定義和管理研究工作流程。通過 `build_graph` 函數，它將各個研究節點連接起來，形成一個完整的工作流程圖。這種基於圖的設計使得系統能夠靈活地處理複雜的研究過程，並且能夠根據研究的進展動態調整工作流程。
