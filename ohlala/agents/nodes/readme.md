# 概述

`shandu/agents/nodes` 目錄包含了 Shandu 研究系統中的各個處理節點，這些節點組成了完整的研究工作流程圖（LangGraph）。每個節點負責研究過程中的特定任務，從初始化研究計劃到生成最終報告。

## 主要節點

根據代碼庫，`shandu/agents/nodes` 目錄中包含以下主要節點：

### 1. 初始化節點 (initialize.py)

初始化節點是研究工作流程的起點，負責創建研究計劃並設置初始狀態 [initialize.py:36-41](#)。

這個節點的主要功能包括：
- 設置研究開始時間和當前日期
- 使用 LLM 生成結構化的研究計劃
- 解析研究計劃並格式化為 Markdown
- 將研究計劃添加到狀態中

### 2. 搜索節點 (search.py)

搜索節點負責執行查詢並處理搜索結果，是獲取研究信息的關鍵節點 [search.py:33-46](#)。

搜索節點的主要功能包括：
- 執行子查詢
- 使用多個搜索引擎並行搜索
- 過濾相關 URL
- 抓取網頁內容
- 分析抓取的內容

### 3. 引用節點 (citations.py)

引用節點負責處理和格式化研究中使用的來源引用 [citations.py:22-28](#)。

引用節點的主要功能包括：
- 註冊選定的來源
- 使用 `CitationManager` 追踪來源和學習內容
- 格式化引用

### 4. 報告生成節點 (report_generation.py)

報告生成節點負責將研究結果轉換為結構化的研究報告 [report_generation.py:42-45](#)。

報告生成過程包括多個子節點：
- `generate_initial_report_node`: 生成初始報告
- `enhance_report_node`: 增強報告內容
- `expand_key_sections_node`: 擴展關鍵部分
- `report_node`: 最終化報告

## 節點之間的連接

這些節點通過 LangGraph 狀態圖連接在一起，形成完整的研究工作流程。在 `shandu/agents/langgraph_agent.py` 中，我們可以看到這些節點是如何連接的 [langgraph_agent.py:83-94](#)。

工作流程的基本順序是：
1. 初始化節點 (initialize)
2. 反思節點 (reflect)
3. 生成查詢節點 (generate_queries)
4. 搜索節點 (search)
5. 智能來源選擇節點 (smart_source_selection)
6. 引用節點 (citations)
7. 報告生成節點 (initial_report, enhance, expand_sections, final_report)

## 節點的狀態管理

所有節點都使用 `AgentState` 對象來維護和傳遞狀態。每個節點接收當前狀態，處理它，然後返回更新後的狀態給下一個節點。

## 節點的執行流程

當用戶通過 CLI 啟動研究過程時，系統會創建 `ResearchGraph` 並執行研究 [cli.py:363-404](#)。

整個流程是通過 LangGraph 狀態圖自動執行的，從初始化節點開始，然後根據條件和狀態轉換到後續節點。

## 節點的迭代過程

Shandu 系統的一個關鍵特點是查詢生成和搜索的迭代過程。在初始查詢生成和搜索之後，系統會進入反思節點，然後再次生成新的查詢，形成一個迭代循環 [agent.py:205-214](#)。

這種迭代方法允許系統根據已發現的信息不斷調整和改進其搜索策略。

## 總結

`shandu/agents/nodes` 目錄包含了 Shandu 研究系統的核心處理節點，這些節點共同組成了完整的研究工作流程。從初始化研究計劃到生成最終報告，每個節點負責特定的任務，並通過 LangGraph 狀態圖連接在一起。這種模塊化的設計使系統能夠進行深入、全面的研究，並生成高質量的研究報告。
