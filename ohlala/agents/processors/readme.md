# 概述

`shandu/agents/processors` 是 Shandu 系統中負責內容處理和報告生成的模組。根據代碼庫，這個目錄主要包含兩個重要的處理器：

- **Content Processor**: 處理搜索結果、提取內容和分析信息
- **Report Generator**: 將研究發現轉換為結構化報告

## 主要組件

### 1. Content Processor

`content_processor.py` 定義了 `AgentState` 類型，這是整個研究系統中用於維護狀態的核心數據結構 [content_processor.py:25-30](#)。

`AgentState` 存儲了研究過程中的所有重要信息，包括查詢、發現、來源、子查詢等。

### 2. Report Generator

`report_generator.py` 是一個更複雜的組件，負責將研究結果轉換為專業的研究報告。它包含多個關鍵功能：

- **結構化輸出模型**  
  `Report Generator` 使用 Pydantic 模型來定義報告的結構 [report_generator.py:11-20](#)。這些模型確保生成的報告具有一致的結構和格式。

- **標題生成**  
  `generate_title` 函數負責為研究報告生成專業、簡潔的標題 [report_generator.py:37-41](#)。這個函數使用 LLM 生成符合特定要求的標題，例如簡潔（最多8個單詞）、描述性強、專業性高 [report_generator.py:43-60](#)。

- **主題提取**  
  `extract_themes` 函數從研究發現中提取關鍵主題，用於構建報告結構 [report_generator.py:110-116](#)。

- **引用格式化**  
  `format_citations` 函數將選定的來源格式化為適當的引用格式 [report_generator.py:181-186](#)。

- **報告生成**  
  `generate_initial_report` 函數是報告生成的核心，它整合了標題、主題、引用等元素，生成完整的研究報告 [report_generator.py:300-312](#)。

- **報告增強和擴展**  
  `Report Generator` 還包含 `enhance_report` 和 `expand_key_sections` 函數，用於增強報告的詳細程度和擴展關鍵部分 [report_generator.py:448-456](#), [report_generator.py:542-548](#)。

## 與其他組件的集成

`processors` 模組與 Shandu 系統的其他組件緊密集成：

- **與 Nodes 的集成**  
  `report_generation.py` 節點使用 `Report Generator` 的功能來生成報告 [report_generation.py:10-17](#)。

- **與 Utils 的集成**  
  `Report Generator` 使用 `citation_manager` 和 `citation_registry` 來管理引用 [report_generation.py:49-55](#)。

## 模組導出

`__init__.py` 文件定義了 `processors` 模組導出的組件 [__init__.py:4-17](#)，這確保了其他模組可以方便地導入和使用這些處理器。

## 錯誤處理

`Report Generator` 包含全面的錯誤處理機制，確保即使在出現問題時也能生成報告 [report_generator.py:156-158](#)。

## 總結

`shandu/agents/processors` 是 Shandu 研究系統的核心組件，負責處理研究內容和生成專業的研究報告。它包含兩個主要組件：`Content Processor` 和 `Report Generator`，前者處理研究數據，後者將這些數據轉換為結構化報告。這些處理器與系統的其他部分緊密集成，共同支持 Shandu 的研究功能。
