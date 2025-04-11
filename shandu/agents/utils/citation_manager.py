"""
Citation management system for tracking sources and their associated learnings.
Provides functionality to link specific information with web sources and manage citations.
"""
from typing import Dict, Any, List, Optional, Set, Union, Tuple
from dataclasses import dataclass, field
import re
import json
import time
import hashlib
from urllib.parse import urlparse
from .citation_registry import CitationRegistry

@dataclass
class SourceInfo:
    """Detailed information about a source."""
    url: str
    title: str = ""
    snippet: str = ""
    source_type: str = ""  # e.g., "web", "academic", "news"
    content_type: str = ""  # e.g., "article", "blog", "paper"
    access_time: float = 0.0
    domain: str = ""
    reliability_score: float = 0.0  # 0.0 to 1.0
    extracted_content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize additional fields after creation."""
        if not self.domain and self.url:
            parsed_url = urlparse(self.url)
            self.domain = parsed_url.netloc

@dataclass
class Learning:
    """A specific piece of information learned from sources."""
    content: str
    sources: List[str] = field(default_factory=list)  # List of source URLs
    confidence: float = 1.0  # How confident we are about this information (0.0 to 1.0)
    category: str = ""  # e.g., "fact", "opinion", "definition"
    context: str = ""  # Additional context about how this information was derived
    source_quotes: List[str] = field(default_factory=list)  # Direct quotes supporting this learning
    hash_id: str = ""  # Unique identifier for deduplication
    
    def __post_init__(self):
        """Initialize hash_id if not provided."""
        if not self.hash_id:

            self.hash_id = hashlib.md5(self.content.encode('utf-8')).hexdigest()

class CitationManager:
    """
    Enhanced citation manager that tracks the relationship between sources and learnings.
    Provides functionality to link specific information with the sources it came from.
    """
    def __init__(self):
        self.sources: Dict[str, SourceInfo] = {}  # Maps URL to SourceInfo
        self.learnings: Dict[str, Learning] = {}  # Maps hash_id to Learning
        self.source_to_learnings: Dict[str, List[str]] = {}  # Maps source URL to list of learning hash_ids
        self.citation_registry = CitationRegistry()  # For backward compatibility
        self.learning_categories = set()  # Track all used categories
        
    def add_source(self, source_info: SourceInfo) -> str:
        """
        Add or update a source in the manager.
        
        Args:
            source_info: The SourceInfo object containing source details
            
        Returns:
            str: The URL of the source
        """
        url = source_info.url
        if url not in self.sources:
            self.source_to_learnings[url] = []

            if not source_info.access_time:
                source_info.access_time = time.time()
        
        self.sources[url] = source_info
        return url
    
    def add_learning(self, learning: Learning) -> str:
        """
        Add a new piece of learning and associate it with sources.
        
        Args:
            learning: The Learning object containing the information and its sources
            
        Returns:
            str: The hash_id of the learning
        """

        existing_hash = self._find_similar_learning(learning.content)
        if existing_hash:

            existing = self.learnings[existing_hash]

            for source_url in learning.sources:
                if source_url not in existing.sources:
                    existing.sources.append(source_url)
                    # Also update the reverse mapping
                    if source_url in self.source_to_learnings:
                        if existing_hash not in self.source_to_learnings[source_url]:
                            self.source_to_learnings[source_url].append(existing_hash)

            if learning.confidence != 1.0:
                # Use weighted average for confidence updates
                existing.confidence = (existing.confidence + learning.confidence) / 2
            
            if learning.category and not existing.category:
                existing.category = learning.category
                self.learning_categories.add(learning.category)
                
            if learning.context and learning.context not in existing.context:
                if existing.context:
                    existing.context += f" {learning.context}"
                else:
                    existing.context = learning.context

            for quote in learning.source_quotes:
                if quote not in existing.source_quotes:
                    existing.source_quotes.append(quote)
                    
            return existing_hash

        hash_id = learning.hash_id
        self.learnings[hash_id] = learning

        for source_url in learning.sources:
            if source_url not in self.source_to_learnings:
                self.source_to_learnings[source_url] = []
            self.source_to_learnings[source_url].append(hash_id)

            if source_url not in self.sources:
                self.add_source(SourceInfo(url=source_url))
                
        # Track category
        if learning.category:
            self.learning_categories.add(learning.category)
                
        return hash_id
    
    def _find_similar_learning(self, content: str) -> Optional[str]:
        """
        Find a learning with similar content using fuzzy matching.
        
        Args:
            content: The content to match
            
        Returns:
            Optional[str]: The hash_id of a similar learning, or None if no match
        """
        # Normalize the content for comparison
        normalized = self._normalize_text(content)
        
        # First try exact matches on normalized content
        for hash_id, learning in self.learnings.items():
            if self._normalize_text(learning.content) == normalized:
                return hash_id
                
        # If no exact match, try fuzzy matching for very similar content
        # This is a simplified implementation - could be enhanced with better NLP techniques
        for hash_id, learning in self.learnings.items():
            similarity = self._calculate_similarity(normalized, self._normalize_text(learning.content))
            if similarity > 0.8:  # Threshold can be adjusted
                return hash_id
                
        return None
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison by removing extra whitespace and lowercasing."""
        text = re.sub(r'\s+', ' ', text).strip().lower()
        # Remove common punctuation for better matching
        text = re.sub(r'[,.;:!?"\']', '', text)
        return text
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate a similarity score between two texts.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            float: Similarity score from 0.0 to 1.0
        """
        # Simple character-level Jaccard similarity
        # This could be enhanced with more sophisticated NLP techniques
        if not text1 or not text2:
            return 0.0
            
        set1 = set(text1)
        set2 = set(text2)
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def get_learnings_from_source(self, source_url: str) -> List[Learning]:
        """
        Get all learnings associated with a specific source.
        
        Args:
            source_url: URL of the source
            
        Returns:
            List[Learning]: List of Learning objects associated with this source
        """
        if source_url not in self.source_to_learnings:
            return []
            
        learning_ids = self.source_to_learnings[source_url]
        return [self.learnings[lid] for lid in learning_ids if lid in self.learnings]
    
    def get_sources_for_learning(self, learning_hash: str) -> List[SourceInfo]:
        """
        Get all sources associated with a specific learning.
        
        Args:
            learning_hash: Hash ID of the learning
            
        Returns:
            List[SourceInfo]: List of SourceInfo objects associated with this learning
        """
        if learning_hash not in self.learnings:
            return []
            
        source_urls = self.learnings[learning_hash].sources
        return [self.sources[url] for url in source_urls if url in self.sources]
    
    def extract_learning_from_text(self, text: str, source_url: str, context: str = "") -> List[str]:
        """
        Extract and register learnings from text content, associating them with a source.
        
        Args:
            text: The text to extract learnings from
            source_url: URL of the source
            context: Additional context about this extraction
            
        Returns:
            List[str]: List of learning hash IDs that were extracted
        """
        # This is a placeholder - in a real implementation, you might use NLP or an LLM to extract facts
        # For now, we'll just treat each paragraph as a separate learning
        paragraphs = re.split(r'\n\s*\n', text)
        learning_hashes = []
        
        for p in paragraphs:
            p = p.strip()
            if len(p) < 20:  # Skip very short paragraphs
                continue
                
            learning = Learning(
                content=p,
                sources=[source_url],
                context=context,
                source_quotes=[p]  # The entire paragraph is a quote in this simple implementation
            )
            
            hash_id = self.add_learning(learning)
            learning_hashes.append(hash_id)
            
        return learning_hashes
    
    def get_citations_for_report(self, report_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Process a report to find, verify, and format citations.
        
        Args:
            report_text: The text of the report
            
        Returns:
            Tuple[str, List[Dict]]: The processed text with proper citations and the bibliography entries
        """

        citation_pattern = re.compile(r'\[(\d+)\]')
        used_citation_ids = set(int(cid) for cid in citation_pattern.findall(report_text) if cid.isdigit())

        bibliography = []
        
        for cid in sorted(used_citation_ids):

            reg_id = self.citation_registry.register_citation(f"citation-{cid}")
            
            # Try to find the corresponding source
            source_info = None
            for source in self.sources.values():
                # This matching logic would need to be enhanced in a real implementation
                if str(cid) in source.url or (hasattr(source, 'citation_id') and source.citation_id == cid):
                    source_info = source
                    break
            
            if source_info:
                entry = {
                    "id": cid,
                    "url": source_info.url,
                    "title": source_info.title or "Unknown Title",
                    "source_type": source_info.source_type or "web",
                    "accessed": time.strftime("%Y-%m-%d", time.localtime(source_info.access_time)) 
                        if source_info.access_time else "Unknown Date"
                }
                bibliography.append(entry)
            else:
                # If we don't have info, create a placeholder
                bibliography.append({
                    "id": cid,
                    "url": f"unknown-source-{cid}",
                    "title": "Unknown Source",
                    "source_type": "unknown",
                    "accessed": "Unknown Date"
                })

        processed_text = report_text
        
        return processed_text, bibliography
    
    def format_bibliography(self, entries: List[Dict[str, Any]], style: str = "apa") -> str:
        """
        Format bibliography entries according to the specified citation style.
        
        Args:
            entries: List of bibliography entries
            style: Citation style to use ("apa", "mla", "chicago", etc.)
            
        Returns:
            str: Formatted bibliography
        """
        if not entries:
            return "No sources cited."
            
        bibliography = "# References\n\n"
        
        for entry in sorted(entries, key=lambda e: e["id"]):
            if style == "apa":
                bib_entry = f"[{entry['id']}] "
                if entry.get("title"):
                    bib_entry += f"{entry['title']}. "
                if entry.get("url"):
                    bib_entry += f"Retrieved from {entry['url']} "
                if entry.get("accessed"):
                    bib_entry += f"on {entry['accessed']}."
                    
                bibliography += bib_entry + "\n\n"
                
            elif style == "mla":
                bib_entry = f"[{entry['id']}] "
                if entry.get("title"):
                    bib_entry += f'"{entry["title"]}." '
                if entry.get("url"):
                    bib_entry += f"{entry['url']}, "
                if entry.get("accessed"):
                    bib_entry += f"accessed {entry['accessed']}."
                    
                bibliography += bib_entry + "\n\n"
                
            else:  # Default format
                bib_entry = f"[{entry['id']}] {entry.get('title', 'Unknown Title')}. {entry.get('url', 'No URL')}."
                bibliography += bib_entry + "\n\n"
                
        return bibliography
    
    def get_learning_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the learnings and sources.
        
        Returns:
            Dict[str, Any]: Statistics about learnings and sources
        """
        stats = {
            "total_sources": len(self.sources),
            "total_learnings": len(self.learnings),
            "categories": list(self.learning_categories),
            "sources_by_domain": self._count_sources_by_domain(),
            "learnings_by_category": self._count_learnings_by_category(),
            "source_reliability": self._calculate_source_reliability()
        }
        return stats
    
    def _count_sources_by_domain(self) -> Dict[str, int]:
        """Count sources by domain."""
        domain_count = {}
        for source in self.sources.values():
            domain = source.domain
            domain_count[domain] = domain_count.get(domain, 0) + 1
        return domain_count
    
    def _count_learnings_by_category(self) -> Dict[str, int]:
        """Count learnings by category."""
        category_count = {}
        for learning in self.learnings.values():
            category = learning.category or "uncategorized"
            category_count[category] = category_count.get(category, 0) + 1
        return category_count
    
    def _calculate_source_reliability(self) -> Dict[str, float]:
        """Calculate average reliability scores by domain."""
        domain_reliability = {}
        domain_counts = {}
        
        for source in self.sources.values():
            if source.reliability_score > 0:
                domain = source.domain
                if domain not in domain_reliability:
                    domain_reliability[domain] = 0
                    domain_counts[domain] = 0
                domain_reliability[domain] += source.reliability_score
                domain_counts[domain] += 1

        avg_reliability = {}
        for domain, total in domain_reliability.items():
            count = domain_counts[domain]
            avg_reliability[domain] = total / count if count > 0 else 0
            
        return avg_reliability
    
    def export_to_json(self, path: str) -> bool:
        """
        Export the citation manager data to a JSON file.
        
        Args:
            path: Path to save the JSON file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            data = {
                "sources": {url: self._source_to_dict(source) for url, source in self.sources.items()},
                "learnings": {hash_id: self._learning_to_dict(learning) for hash_id, learning in self.learnings.items()},
                "source_to_learnings": self.source_to_learnings,
                "learning_categories": list(self.learning_categories),
                "export_time": time.time()
            }
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error exporting citation data: {e}")
            return False
    
    def import_from_json(self, path: str) -> bool:
        """
        Import citation manager data from a JSON file.
        
        Args:
            path: Path to the JSON file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Clear existing data
            self.sources.clear()
            self.learnings.clear()
            self.source_to_learnings.clear()
            self.learning_categories.clear()

            for url, source_dict in data.get("sources", {}).items():
                self.sources[url] = self._dict_to_source(source_dict)

            for hash_id, learning_dict in data.get("learnings", {}).items():
                self.learnings[hash_id] = self._dict_to_learning(learning_dict)

            self.source_to_learnings = data.get("source_to_learnings", {})

            self.learning_categories = set(data.get("learning_categories", []))
            
            return True
        except Exception as e:
            print(f"Error importing citation data: {e}")
            return False
    
    def _source_to_dict(self, source: SourceInfo) -> Dict[str, Any]:
        """Convert a SourceInfo object to a dictionary."""
        return {
            "url": source.url,
            "title": source.title,
            "snippet": source.snippet,
            "source_type": source.source_type,
            "content_type": source.content_type,
            "access_time": source.access_time,
            "domain": source.domain,
            "reliability_score": source.reliability_score,
            "metadata": source.metadata
        }
    
    def _dict_to_source(self, source_dict: Dict[str, Any]) -> SourceInfo:
        """Convert a dictionary to a SourceInfo object."""
        return SourceInfo(
            url=source_dict["url"],
            title=source_dict.get("title", ""),
            snippet=source_dict.get("snippet", ""),
            source_type=source_dict.get("source_type", ""),
            content_type=source_dict.get("content_type", ""),
            access_time=source_dict.get("access_time", 0.0),
            domain=source_dict.get("domain", ""),
            reliability_score=source_dict.get("reliability_score", 0.0),
            metadata=source_dict.get("metadata", {})
        )
    
    def _learning_to_dict(self, learning: Learning) -> Dict[str, Any]:
        """Convert a Learning object to a dictionary."""
        return {
            "content": learning.content,
            "sources": learning.sources,
            "confidence": learning.confidence,
            "category": learning.category,
            "context": learning.context,
            "source_quotes": learning.source_quotes,
            "hash_id": learning.hash_id
        }
    
    def _dict_to_learning(self, learning_dict: Dict[str, Any]) -> Learning:
        """Convert a dictionary to a Learning object."""
        return Learning(
            content=learning_dict["content"],
            sources=learning_dict.get("sources", []),
            confidence=learning_dict.get("confidence", 1.0),
            category=learning_dict.get("category", ""),
            context=learning_dict.get("context", ""),
            source_quotes=learning_dict.get("source_quotes", []),
            hash_id=learning_dict.get("hash_id", "")
        )