import unittest
from unittest.mock import AsyncMock, patch
import asyncio
from ohlala.agents.processors.report_generator import format_citations
from ohlala.agents.utils.citation_registry import CitationRegistry

class TestReportGenerator(unittest.TestCase):
    """報告生成函數的基本測試。"""
    
    def setUp(self):
        """設定測試用例。"""
        self.mock_llm = AsyncMock()
        self.mock_llm.ainvoke = AsyncMock()
        
        # 示例引用數據
        self.sample_sources = [
            {"url": "https://example.com/article1", "title": "測試文章 1", "date": "2023-01-01"},
            {"url": "https://github.com/user/repo", "title": "示例倉庫", "date": "2024-02-15"}
        ]
        
        # 創建一個引用註冊表
        self.registry = CitationRegistry()
        self.registry.register_citation("https://example.com/article1")
        self.registry.register_citation("https://github.com/user/repo")
        
        # 向引用添加元數據
        self.registry.update_citation_metadata(1, {
            "title": "測試文章 1",
            "date": "2023-01-01"
        })
        self.registry.update_citation_metadata(2, {
            "title": "示例倉庫",
            "date": "2024-02-15"
        })
    
    def test_format_citations_sync(self):
        """通過運行異步函數同步測試format_citations函數。"""
        # 設置模擬對象以返回格式正確的引用
        self.mock_llm.ainvoke.return_value.content = """
        [1] *example.com*, "測試文章 1", https://example.com/article1
        [2] *github.com*, "示例倉庫", https://github.com/user/repo
        """
        
        # 在同步上下文中運行異步函數
        formatted_citations = asyncio.run(format_citations(
            self.mock_llm,
            ["https://example.com/article1", "https://github.com/user/repo"],
            self.sample_sources,
            self.registry
        ))
        
        # 檢查結果
        self.assertIn("*example.com*", formatted_citations)
        self.assertIn("\"測試文章 1\"", formatted_citations)
        self.assertIn("https://example.com/article1", formatted_citations)
        
        # 驗證正確的格式（引用中無日期）
        self.assertNotIn("2023-01-01", formatted_citations)
        self.assertNotIn("2024-02-15", formatted_citations)
        
        # 確保引用編號格式正確
        self.assertIn("[1]", formatted_citations)
        self.assertIn("[2]", formatted_citations)

if __name__ == '__main__':
    unittest.main()
