# CitationManager

`CitationManager` 是 Shandu 系統中的一個核心組件，位於 `shandu/agents/utils/citation_manager.py`。它提供了全面的引用管理功能，用於追踪信息來源及其相關學習內容。

## 主要功能

- **來源追踪**：記錄和管理研究過程中使用的所有信息來源 [citation_manager.py:56-60](#)
- **知識提取**：從來源中提取和存儲特定的知識點（"learnings"） [citation_manager.py:34-42](#)
- **引用格式化**：為研究報告生成適當格式的引用和參考文獻 [citation_manager.py:51-55](#)

## 數據結構

`CitationManager` 使用兩個主要的數據類：

- **SourceInfo**：存儲來源信息的詳細數據 [citation_manager.py:14-26](#)
- **Learning**：表示從來源中提取的特定知識點 [citation_manager.py:34-42](#)

## 主要方法

- **add_source**：添加或更新來源信息 [citation_manager.py:63-81](#)
- **add_learning**：添加新的知識點並關聯到來源 [citation_manager.py:83-92](#)
- **extract_learning_from_text**：從文本中提取知識點 [citation_manager.py:234-266](#)
- **get_learning_statistics**：獲取關於學習和來源的統計信息 [citation_manager.py:365-380](#)
- **export_to_json** 和 **import_from_json**：保存和加載引用數據 [citation_manager.py:419-443](#)

## 與研究系統的集成

`CitationManager` 與 Shandu 研究系統的其他組件緊密集成，特別是與 `ResearchAgent` 和報告生成節點：[agent.py:42-43](#)

在研究過程中，`CitationManager` 用於：
- 註冊搜索結果和抓取的網頁內容作為來源
- 從內容分析中提取知識點
- 為最終報告生成引用和參考文獻 [report_generation.py:49-55](#)

## 其他實用工具

除了 `CitationManager`，`shandu/utils` 目錄還包含其他實用工具，例如：
- **citation_registry.py**：提供與 `CitationManager` 兼容的引用註冊功能 [citation_manager.py:12](#)
- **agent_utils.py**：包含用於代理操作的實用函數，如日誌記錄和進度回調 [report_generation.py:18](#)
- **logger.py**：提供系統日誌記錄功能 [report_generator.py:156-158](#)

## 統計和分析功能

`CitationManager` 提供了強大的統計和分析功能，用於評估研究質量和來源可靠性：[citation_manager.py:372-379](#)

這些統計數據包括：
- 來源總數和知識點總數
- 按類別分類的知識點
- 按域名分類的來源
- 按域名計算的來源可靠性

## 總結

`shandu/utils` 模組是 Shandu 研究系統的核心支持組件，提供了引用管理、知識提取和各種實用功能。其中最重要的組件是 `CitationManager`，它確保研究過程中的所有信息都能被適當地追踪和引用，從而提高研究報告的可靠性和專業性。
