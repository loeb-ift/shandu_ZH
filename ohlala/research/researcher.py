"""Research module implementation."""
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import os

@dataclass
class ResearchResult:
    """Container for research results with enhanced citation tracking."""
    query: str
    summary: str
    sources: List[Dict[str, Any]]
    subqueries: List[str]
    depth: int
    content_analysis: Optional[List[Dict[str, Any]]] = None
    chain_of_thought: Optional[List[str]] = None
    research_stats: Optional[Dict[str, Any]] = None
    citation_stats: Optional[Dict[str, Any]] = None  # 用於追蹤引用統計的新字段
    timestamp: datetime = field(default_factory=datetime.now)

    def to_markdown(self, include_chain_of_thought: bool = False, include_objective: bool = False) -> str:
        """將研究結果轉換為包含引用統計的Markdown格式。"""
        stats = self.research_stats or {}
        elapsed_time = stats.get("elapsed_time_formatted", "未知")
        sources_count = stats.get("sources_count", len(self.sources))
        subqueries_count = stats.get("subqueries_count", len(self.subqueries))

        citation_stats = self.citation_stats or {}
        total_sources = citation_stats.get("total_sources", sources_count)
        total_learnings = citation_stats.get("total_learnings", 0)

        summary = self.summary

        lines = summary.split("\n")
        
        # 移除可能出現在輸出中的特定工件
        cleaned_lines = []
        for line in lines:
            # 跳過具有這些模式的行
            if (line.strip().startswith("*Generated on:") or 
                line.strip().startswith("Completed:") or 
                "Here are" in line and ("search queries" in line or "queries to investigate" in line) or
                line.strip() == "Research Framework:" or
                "Key Findings:" in line or
                "Key aspects to focus on:" in line):
                continue
            cleaned_lines.append(line)
            
        summary = "\n".join(cleaned_lines)
        
        # 修正 "Research Report: **Objective:**" 格式問題
        if summary.startswith("# Research Report: **Objective:**"):
            summary = summary.replace("# Research Report: **Objective:**", "# Research Report")
        
        # 如果未請求，則移除目標部分
        if not include_objective and "**Objective:**" in summary:
            # 按部分分割
            parts = summary.split("## ")
            filtered_parts = []

            for part in parts:
                # 保留執行摘要或空白部分
                if part.startswith("Executive Summary") or not part.strip():
                    filtered_parts.append(part)
                    continue
                
                # 跳過目標部分
                if "**Objective:**" in part and "**Key Aspects to Focus On:**" in part:
                    continue
                
                # 保留其他部分
                filtered_parts.append(part)
            
            # 重構摘要
            if filtered_parts:
                if not filtered_parts[0].startswith("Executive Summary"):
                    summary = "## ".join(filtered_parts)
                else:
                    summary = filtered_parts[0] + "## " + "## ".join(filtered_parts[1:])

        md = [
            f"# {self.query}\n",
            f"{summary}\n"
        ]

        md.append("## 研究過程\n")
        md.append(f"- **深度**: {self.depth}")
        md.append(f"- **廣度**: {stats.get('breadth', '未指定')}")
        md.append(f"- **耗時**: {elapsed_time}")
        md.append(f"- **探索的子查詢**: {subqueries_count}")
        md.append(f"- **分析的來源**: {sources_count}")

        if total_learnings > 0:
            md.append(f"- **提取的總學習內容**: {total_learnings}")
            md.append(f"- **來源覆蓋率**: {total_sources} 個來源，包含 {total_learnings} 個追蹤信息點")

            source_reliability = citation_stats.get("source_reliability", {})
            if source_reliability:
                md.append(f"- **來源質量**: {len(source_reliability)} 個域名進行了可靠性評估\n")
            else:
                md.append("")
        else:
            md.append("")

        if include_chain_of_thought and self.chain_of_thought:
            md.append("## 研究過程：思考鏈\n")
            significant_thoughts = []
            
            for thought in self.chain_of_thought:
                # 跳過通用或重複的思考以及輸出工件
                if any(x in thought.lower() for x in [
                    "searching for", "selected relevant url", "completed", 
                    "here are", "generated search queries", "queries to investigate"
                ]):
                    continue
                significant_thoughts.append(thought)
            
            if len(significant_thoughts) > 20:
                selected_thoughts = (
                    significant_thoughts[:5] + 
                    significant_thoughts[len(significant_thoughts)//2-2:len(significant_thoughts)//2+3] + 
                    significant_thoughts[-5:]
                )
            else:
                selected_thoughts = significant_thoughts
                
            for thought in selected_thoughts:
                md.append(f"- {thought}")
            md.append("")
        
        return "\n".join(md)

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式。"""
        result = {
            "query": self.query,
            "summary": self.summary,
            "sources": self.sources,
            "subqueries": self.subqueries,
            "depth": self.depth,
            "content_analysis": self.content_analysis,
            "chain_of_thought": self.chain_of_thought,
            "research_stats": self.research_stats,
            "timestamp": self.timestamp.isoformat()
        }

        if self.citation_stats:
            result["citation_stats"] = self.citation_stats
            
        return result
    
    def save_to_file(self, filepath: str, include_chain_of_thought: bool = False, include_objective: bool = False) -> None:
        """將研究結果保存到文件。"""
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)
        
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()
        
        if ext == '.md':
            # 保存為Markdown
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.to_markdown(include_chain_of_thought, include_objective))
        elif ext == '.json':
            # 保存為JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
        else:
            # 默認為Markdown
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.to_markdown(include_chain_of_thought, include_objective))
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchResult':
        """從字典創建一個ResearchResult對象。"""
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            
        return cls(**data)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'ResearchResult':
        """從文件加載研究結果。"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls.from_dict(data)

class DeepResearcher:
    """研究協調器。"""
    def __init__(
        self,
        output_dir: Optional[str] = None,
        save_results: bool = True,
        auto_save_interval: Optional[int] = None
    ):
        """初始化研究器。"""
        self.output_dir = output_dir or os.path.expanduser("~/shandu_research")
        self.save_results = save_results
        self.auto_save_interval = auto_save_interval
        
        if self.save_results:
            os.makedirs(self.output_dir, exist_ok=True)
    
    def get_output_path(self, query: str, format: str = 'md') -> str:
        """獲取研究結果的輸出路徑。"""
        sanitized = "".join(c if c.isalnum() or c in " -_" else "_" for c in query)
        sanitized = sanitized[:50]
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{sanitized}_{timestamp}.{format}"
        
        return os.path.join(self.output_dir, filename)
    
    async def research(
        self, 
        query: str,
        strategy: str = 'langgraph',
        **kwargs
    ) -> ResearchResult:
        """使用指定的策略執行研究。"""
        from ..agents.langgraph_agent import ResearchGraph
        from ..agents.agent import ResearchAgent
        
        result = None
        
        if strategy == 'langgraph':
            graph = ResearchGraph()
            result = await graph.research(query, **kwargs)
        elif strategy == 'agent':
            agent = ResearchAgent()
            result = await agent.research(query, **kwargs)
        else:
            raise ValueError(f"未知的研究策略: {strategy}")
        
        if self.save_results and result:
            md_path = self.get_output_path(query, 'md')
            result.save_to_file(md_path)
            
            json_path = self.get_output_path(query, 'json')
            result.save_to_file(json_path)
        
        return result
    
    def research_sync(
        self, 
        query: str,
        strategy: str = 'langgraph',
        **kwargs
    ) -> ResearchResult:
        """同步研究包裝器。"""
        import asyncio
        return asyncio.run(self.research(query, strategy, **kwargs))
