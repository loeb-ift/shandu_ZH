import unittest
from shandu.agents.utils.citation_registry import CitationRegistry

class TestCitationRegistry(unittest.TestCase):
    """CitationRegistry類的基本測試。"""
    
    def test_citation_registration(self):
        """測試引用是否可以正確註冊和檢索。"""
        registry = CitationRegistry()
        
        # 註冊一些引用
        cid1 = registry.register_citation("https://example.com/article1")
        cid2 = registry.register_citation("https://example.com/article2")
        cid3 = registry.register_citation("https://example.com/article3")
        
        # 測試引用ID是否按順序排列
        self.assertEqual(cid1, 1)
        self.assertEqual(cid2, 2)
        self.assertEqual(cid3, 3)
        
        # 測試URL到ID的映射是否正常工作
        self.assertEqual(registry.url_to_id["https://example.com/article1"], 1)
        self.assertEqual(registry.url_to_id["https://example.com/article2"], 2)
        
        # 測試ID到URL的映射是否正常工作
        self.assertEqual(registry.id_to_url[1], "https://example.com/article1")
        self.assertEqual(registry.id_to_url[2], "https://example.com/article2")
        
        # 測試獲取引用信息
        self.assertEqual(registry.get_citation_info(1)["url"], "https://example.com/article1")
        self.assertEqual(registry.get_citation_info(2)["url"], "https://example.com/article2")
    
    def test_bulk_registration(self):
        """測試批量註冊引用。"""
        registry = CitationRegistry()
        
        urls = [
            "https://example.com/article1",
            "https://example.com/article2",
            "https://example.com/article3"
        ]
        
        registry.bulk_register_sources(urls)
        
        # 檢查所有URL是否都已註冊
        self.assertEqual(len(registry.citations), 3)
        
        # 檢查URL到ID的映射
        self.assertIn("https://example.com/article1", registry.url_to_id)
        self.assertIn("https://example.com/article2", registry.url_to_id)
        self.assertIn("https://example.com/article3", registry.url_to_id)
    
    def test_citation_validation(self):
        """測試文本中引用的驗證。"""
        registry = CitationRegistry()
        
        # 註冊一些引用
        registry.register_citation("https://example.com/article1")
        registry.register_citation("https://example.com/article2")
        
        # 包含有效和無效引用的文本
        text = """
        這是一個包含有效引用 [1] 和另一個有效引用 [2] 的測試。
        這是一個不存在的無效引用 [3]。
        這裡再次提到 [1] 和一個超出範圍的 [5]。
        """
        
        result = registry.validate_citations(text)
        
        # 檢查驗證結果
        self.assertFalse(result["valid"])
        self.assertIn(3, result["invalid_citations"])
        self.assertIn(5, result["invalid_citations"])
        self.assertEqual(len(result["used_citations"]), 2)
        self.assertIn(1, result["used_citations"])
        self.assertIn(2, result["used_citations"])

if __name__ == '__main__':
    unittest.main()
