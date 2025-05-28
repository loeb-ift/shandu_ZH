"""
Ohlala深度研究系統
一個強大的研究工具，結合了多個搜索引擎並集成了LangChain。

版權所有 (c) 2025 Dušan Jolović
根據MIT許可證授權。有關詳細信息，請參閱LICENSE文件。
"""

from .search.search import UnifiedSearcher, SearchResult
from .research.researcher import DeepResearcher, ResearchResult
from .agents.agent import ResearchAgent

__version__ = "1.5.2"
__all__ = [
    "UnifiedSearcher",
    "SearchResult",
    "DeepResearcher",
    "ResearchResult",
    "ResearchAgent"
]
