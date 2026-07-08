"""
知識庫管理器單元測試

TODO: 實施完整的測試覆蓋 (Phase 2.1+)
"""

import pytest
from claude_lit.knowledge_base import KnowledgeBaseManager


class TestKnowledgeBaseManager:
    """知識庫管理器測試"""

    def test_initialization(self):
        """測試初始化"""
        kb = KnowledgeBaseManager()
        assert kb is not None

    def test_list_papers(self):
        """測試列出論文"""
        kb = KnowledgeBaseManager()
        papers = kb.list_papers(limit=5)
        assert isinstance(papers, list)

    @pytest.mark.skip(reason="待實施")
    def test_search_papers(self):
        """測試搜索論文"""
        kb = KnowledgeBaseManager()
        results = kb.search_papers("deep learning", limit=10)
        assert len(results) > 0

    @pytest.mark.skip(reason="待實施")
    def test_semantic_search(self):
        """測試語義搜索"""
        kb = KnowledgeBaseManager()
        results = kb.semantic_search_papers("neural networks", limit=5)
        assert len(results) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
