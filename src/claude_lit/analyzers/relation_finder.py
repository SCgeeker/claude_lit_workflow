#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relation-Finder 關係分析模組
用於發現論文間的語義關係、共同作者網絡和概念共現
"""

import json
import sqlite3
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent


from claude_lit.knowledge_base.kb_manager import KnowledgeBaseManager
from claude_lit.embeddings.vector_db import VectorDatabase
from claude_lit.utils.content_filter import extract_ai_content

# 嘗試相對導入，失敗則使用絕對導入
try:
    from .zettel_concept_analyzer import ZettelConceptAnalyzer
except ImportError:
    from claude_lit.analyzers.zettel_concept_analyzer import ZettelConceptAnalyzer


# ============================================================
# Phase 2.3 改進: 領域相似度矩陣
# ============================================================
DOMAIN_SIMILARITY_MATRIX = {
    # 認知科學相關
    ('CogSci', 'AI'): 0.8,          # 高度相關（認知模型與AI）
    ('CogSci', 'Linguistics'): 0.8,  # 高度相關（心理語言學）
    ('CogSci', 'Neuroscience'): 0.9, # 極高相關（認知神經科學）
    ('CogSci', 'Psychology'): 0.95,  # 極高相關（認知心理學）

    # AI相關
    ('AI', 'Linguistics'): 0.6,      # 中度相關（NLP）
    ('AI', 'Neuroscience'): 0.7,     # 中高相關（神經網絡）
    ('AI', 'ComputerScience'): 0.9,  # 極高相關

    # 語言學相關
    ('Linguistics', 'Psychology'): 0.7,      # 中高相關（心理語言學）
    ('Linguistics', 'Anthropology'): 0.8,    # 高度相關（人類學語言學）
    ('Linguistics', 'ComputerScience'): 0.5, # 中度相關（計算語言學）

    # 神經科學相關
    ('Neuroscience', 'Psychology'): 0.9,     # 極高相關
    ('Neuroscience', 'Biology'): 0.85,       # 高度相關

    # 其他交叉領域
    ('Psychology', 'Sociology'): 0.7,        # 中高相關（社會心理學）
    ('ComputerScience', 'Mathematics'): 0.8, # 高度相關
}

# 默認相似度（未在矩陣中定義的領域組合）
DEFAULT_DOMAIN_SIMILARITY = 0.3


@dataclass
class Citation:
    """論文引用關係"""
    citing_paper_id: int
    cited_paper_id: int
    citing_title: str
    cited_title: str
    similarity_score: float
    confidence: str
    common_concepts: List[str]

    def __repr__(self) -> str:
        return f"Citation({self.citing_paper_id} → {self.cited_paper_id}, {self.similarity_score:.2f})"


@dataclass
class CoAuthorEdge:
    """共同作者邊"""
    author1: str
    author2: str
    collaboration_count: int
    shared_papers: List[int]


@dataclass
class ConceptPair:
    """概念對"""
    concept1: str
    concept2: str
    co_occurrence_count: int
    papers: List[int]
    association_strength: float


@dataclass
class ConceptRelation:
    """Zettelkasten 概念關係 (Phase 2.1)

    描述兩個 Zettelkasten 卡片之間的語義關係
    """
    card_id_1: str
    card_id_2: str
    card_title_1: str
    card_title_2: str
    relation_type: str  # 6 種: leads_to, based_on, related_to, contrasts_with, superclass_of, subclass_of
    confidence_score: float  # 0.0-1.0
    semantic_similarity: float  # 向量相似度
    link_explicit: bool  # 卡片中是否有明確連結
    shared_concepts: List[str]  # 共同概念
    paper_ids: List[int]  # 關聯的論文 ID

    def __repr__(self) -> str:
        return f"ConceptRelation({self.card_id_1} --{self.relation_type}-> {self.card_id_2}, conf={self.confidence_score:.2f})"


class RelationFinder:
    """關係發現主類"""

    def __init__(self, kb_path: str = "knowledge_base", config: Optional[Dict] = None):
        self.kb = KnowledgeBaseManager(kb_root=kb_path)
        self.config = config or self._default_config()
        self.db_path = Path(kb_path) / "index.db"
        self.zettel_analyzer = ZettelConceptAnalyzer(kb_path=kb_path)

        # Phase 2.1: 向量搜索整合
        try:
            self.vector_db = VectorDatabase(persist_directory="chroma_db")
        except Exception as e:
            print(f"Warning: Could not initialize vector database: {e}")
            self.vector_db = None

    def _default_config(self) -> Dict:
        return {
            'title_similarity_threshold': 0.65,
            'co_author_min_papers': 2,
            'concept_min_frequency': 2,
            'year_range': 5,
        }

    # ========== 0. 安全獲取論文數據 ==========

    def _get_papers_safe(self) -> List[Dict]:
        """從數據庫直接安全地獲取所有論文"""
        papers = []
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, authors, year, keywords FROM papers ORDER BY id")

            for row in cursor.fetchall():
                paper_id, title, authors, year, keywords = row
                paper = {
                    'id': paper_id,
                    'title': title or '',
                    'authors': authors or '[]',
                    'year': year,
                    'keywords': keywords or '[]',
                }
                papers.append(paper)

            conn.close()
        except Exception as e:
            print(f"Warning: Error reading papers: {e}")
            # 回退到 kb_manager
            try:
                papers = self.kb.list_papers(limit=1000)
            except:
                papers = []

        return papers

    # ========== 1. 標題相似度引用關係 ==========

    def find_citations_by_title_similarity(self, threshold: Optional[float] = None) -> List[Citation]:
        """基於標題相似度推測引用關係"""
        threshold = threshold or self.config['title_similarity_threshold']
        papers = self._get_papers_safe()
        citations = []

        for i, paper1 in enumerate(papers):
            for j, paper2 in enumerate(papers):
                if i >= j:
                    continue

                title1 = paper1.get('title', '').lower()
                title2 = paper2.get('title', '').lower()

                words1 = set(title1.split())
                words2 = set(title2.split())

                if not words1 or not words2:
                    continue

                intersection = len(words1 & words2)
                union = len(words1 | words2)
                similarity = intersection / union if union > 0 else 0

                if similarity >= threshold:
                    citation = Citation(
                        citing_paper_id=paper1['id'],
                        cited_paper_id=paper2['id'],
                        citing_title=paper1.get('title', ''),
                        cited_title=paper2.get('title', ''),
                        similarity_score=similarity,
                        confidence=self._get_confidence_level(similarity),
                        common_concepts=self._extract_common_concepts(paper1, paper2),
                    )
                    citations.append(citation)

        return sorted(citations, key=lambda x: x.similarity_score, reverse=True)

    # ========== 2. 共同作者網絡 ==========

    def find_co_authors(self, min_papers: Optional[int] = None) -> Tuple[Dict, List[CoAuthorEdge]]:
        """構建共同作者網絡"""
        min_papers = min_papers or self.config['co_author_min_papers']
        papers = self._get_papers_safe()

        author_papers = defaultdict(list)
        for paper in papers:
            authors = self._parse_authors(paper)
            for author in authors:
                if author:
                    author_papers[author].append(paper['id'])

        co_author_edges = []
        author_list = list(author_papers.keys())

        for i, author1 in enumerate(author_list):
            for author2 in author_list[i+1:]:
                shared_papers = set(author_papers[author1]) & set(author_papers[author2])
                if len(shared_papers) >= min_papers:
                    edge = CoAuthorEdge(
                        author1=author1,
                        author2=author2,
                        collaboration_count=len(shared_papers),
                        shared_papers=sorted(list(shared_papers)),
                    )
                    co_author_edges.append(edge)

        return dict(author_papers), sorted(co_author_edges,
                                          key=lambda x: x.collaboration_count, reverse=True)

    # ========== 3. 概念共現分析 ==========

    def find_co_occurrence(self, min_frequency: Optional[int] = None,
                          top_k: Optional[int] = None) -> List[ConceptPair]:
        """分析概念共現模式"""
        min_frequency = min_frequency or self.config['concept_min_frequency']
        papers = self._get_papers_safe()

        concept_papers = defaultdict(list)
        for paper in papers:
            concepts = self._extract_concepts(paper)
            for concept in concepts:
                if concept:
                    concept_papers[concept].append(paper['id'])

        concept_list = list(concept_papers.keys())
        concept_pairs = []

        for i, concept1 in enumerate(concept_list):
            for concept2 in concept_list[i+1:]:
                shared_papers = set(concept_papers[concept1]) & set(concept_papers[concept2])
                if len(shared_papers) >= min_frequency:
                    max_count = max(len(concept_papers[concept1]), len(concept_papers[concept2]))
                    pair = ConceptPair(
                        concept1=concept1,
                        concept2=concept2,
                        co_occurrence_count=len(shared_papers),
                        papers=sorted(list(shared_papers)),
                        association_strength=len(shared_papers) / max_count,
                    )
                    concept_pairs.append(pair)

        concept_pairs = sorted(concept_pairs,
                              key=lambda x: x.co_occurrence_count, reverse=True)

        if top_k:
            concept_pairs = concept_pairs[:top_k]

        return concept_pairs

    # ========== 4. Mermaid 導出 ==========

    def export_citations_to_mermaid(self, citations: List[Citation],
                                   max_edges: int = 50) -> str:
        """導出引用關係為 Mermaid 圖表"""
        lines = ["```mermaid", "graph TD"]
        seen_nodes = set()

        for citation in citations[:max_edges]:
            node1_id = f'P{citation.citing_paper_id}'
            node2_id = f'P{citation.cited_paper_id}'

            if node1_id not in seen_nodes:
                title = citation.citing_title[:40] + "..." if len(citation.citing_title) > 40 else citation.citing_title
                lines.append(f'    {node1_id}["{title}"]')
                seen_nodes.add(node1_id)

            if node2_id not in seen_nodes:
                title = citation.cited_title[:40] + "..." if len(citation.cited_title) > 40 else citation.cited_title
                lines.append(f'    {node2_id}["{title}"]')
                seen_nodes.add(node2_id)

            if citation.confidence == 'high':
                lines.append(f'    {node1_id} --> {node2_id}')
            else:
                lines.append(f'    {node1_id} -.-> {node2_id}')

        lines.append("```")
        return "\n".join(lines)

    def export_coauthors_to_mermaid(self, author_papers: Dict, edges: List[CoAuthorEdge],
                                   max_edges: int = 30) -> str:
        """導出共同作者網絡為 Mermaid 圖表"""
        lines = ["```mermaid", "graph TD"]

        author_counts = [(a, len(p)) for a, p in author_papers.items()]
        author_counts = sorted(author_counts, key=lambda x: x[1], reverse=True)[:15]
        author_set = {a[0] for a in author_counts}

        lines.append('    subgraph Authors["共同作者網絡"]')
        for author, count in author_counts:
            author_id = f'A{hash(author) % 10000}'
            lines.append(f'        {author_id}["{author} ({count}篇)"]')
        lines.append('    end')

        for edge in edges[:max_edges]:
            if edge.author1 in author_set and edge.author2 in author_set:
                author1_id = f'A{hash(edge.author1) % 10000}'
                author2_id = f'A{hash(edge.author2) % 10000}'
                lines.append(f'    {author1_id} -->|{edge.collaboration_count}| {author2_id}')

        lines.append("```")
        return "\n".join(lines)

    def export_concepts_to_mermaid(self, concepts: List[ConceptPair],
                                  max_pairs: int = 30) -> str:
        """導出概念共現為 Mermaid 圖表"""
        lines = ["```mermaid", "graph TD"]
        seen_concepts = set()

        for pair in concepts[:max_pairs]:
            c1_id = f'C{hash(pair.concept1) % 10000}'
            c2_id = f'C{hash(pair.concept2) % 10000}'

            if pair.concept1 not in seen_concepts:
                concept_name = pair.concept1[:30] + "..." if len(pair.concept1) > 30 else pair.concept1
                lines.append(f'    {c1_id}["{concept_name}"]')
                seen_concepts.add(pair.concept1)

            if pair.concept2 not in seen_concepts:
                concept_name = pair.concept2[:30] + "..." if len(pair.concept2) > 30 else pair.concept2
                lines.append(f'    {c2_id}["{concept_name}"]')
                seen_concepts.add(pair.concept2)

            if pair.association_strength >= 0.5:
                lines.append(f'    {c1_id} --> {c2_id}')
            else:
                lines.append(f'    {c1_id} -.-> {c2_id}')

        lines.append("```")
        return "\n".join(lines)

    # ========== 5. 輔助方法 ==========

    def _get_confidence_level(self, similarity_score: float) -> str:
        if similarity_score >= 0.80:
            return 'high'
        elif similarity_score >= 0.70:
            return 'medium'
        else:
            return 'low'

    def _extract_common_concepts(self, paper1: Dict, paper2: Dict) -> List[str]:
        concepts1 = set(self._extract_concepts(paper1))
        concepts2 = set(self._extract_concepts(paper2))
        return sorted(list(concepts1 & concepts2))

    def _extract_concepts(self, paper: Dict) -> List[str]:
        keywords = paper.get('keywords', '')

        try:
            if isinstance(keywords, str):
                if not keywords or keywords == '[]':
                    return []
                if keywords.startswith('['):
                    try:
                        kw_list = json.loads(keywords)
                        return [k.strip() for k in kw_list if isinstance(k, str) and k.strip()]
                    except (json.JSONDecodeError, ValueError):
                        pass
                return [k.strip() for k in keywords.split(',') if k.strip()]
            elif isinstance(keywords, list):
                return [k.strip() for k in keywords if isinstance(k, str) and k.strip()]
        except Exception:
            pass

        return []

    def _parse_authors(self, paper: Dict) -> List[str]:
        authors_data = paper.get('authors', '')

        try:
            if isinstance(authors_data, str):
                if not authors_data or authors_data == '[]':
                    return []
                if authors_data.startswith('['):
                    try:
                        author_list = json.loads(authors_data)
                        return [a.strip() for a in author_list if isinstance(a, str) and a.strip()]
                    except (json.JSONDecodeError, ValueError):
                        pass
                authors = authors_data.replace(' and ', ',').split(',')
                return [a.strip() for a in authors if a.strip()]
            elif isinstance(authors_data, list):
                return [a.strip() for a in authors_data if isinstance(a, str) and a.strip()]
        except Exception:
            pass

        return []

    # ========== Phase 2.1: Zettelkasten 概念關係識別 ==========

    def find_concept_relations(
        self,
        min_similarity: float = 0.4,
        relation_types: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[ConceptRelation]:
        """識別 Zettelkasten 卡片間的語義關係 (Phase 2.1)

        參數:
            min_similarity: 最小語義相似度閾值（0.0-1.0）
            relation_types: 要識別的關係類型列表，None 表示全部
            limit: 每張卡片檢查的最大相似卡片數

        返回:
            List[ConceptRelation]: 識別出的概念關係列表

        關係類型:
            - leads_to (導向): A → B
            - based_on (基於): A ← B
            - related_to (相關): A ↔ B
            - contrasts_with (對比): A ⊗ B
            - superclass_of (上位概念): A ⊃ B
            - subclass_of (下位概念): A ⊂ B
        """
        if not self.vector_db:
            print("Error: Vector database not initialized")
            return []

        print("\n" + "="*70)
        print("[Phase 2.1] Zettelkasten 概念關係識別")
        print("="*70)

        # 1. 獲取所有 Zettelkasten 卡片
        print("\n[1] 讀取 Zettelkasten 卡片...")
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT zettel_id, title, core_concept, tags, domain, paper_id, content, ai_notes, human_notes
                FROM zettel_cards
                ORDER BY zettel_id
            """)
            cards = []
            for row in cursor.fetchall():
                cards.append({
                    'zettel_id': row[0],
                    'title': row[1],
                    'core_concept': row[2],
                    'tags': row[3],
                    'domain': row[4],
                    'paper_id': row[5],
                    'content': row[6],
                    'ai_notes': row[7],
                    'human_notes': row[8]
                })
            conn.close()
        except Exception as e:
            print(f"Error reading cards: {e}")
            return []

        print(f"   找到 {len(cards)} 張卡片")

        # 2. 對每張卡片找相似卡片
        print(f"\n[2] 使用向量搜索尋找相似卡片...")
        relations = []
        processed_pairs = set()  # 避免重複處理 (A, B) 和 (B, A)

        for i, card in enumerate(cards):
            if (i + 1) % 50 == 0:
                print(f"   進度: {i+1}/{len(cards)} 卡片")

            card_id = card['zettel_id']

            # 使用向量搜索找相似卡片
            try:
                similar_results = self.vector_db.find_similar_zettel(
                    zettel_id=card_id,
                    n_results=min(limit, len(cards) - 1),
                    exclude_self=True
                )
            except Exception as e:
                print(f"   Warning: Failed to find similar cards for {card_id}: {e}")
                continue

            if not similar_results or 'ids' not in similar_results:
                continue

            # 檢查結果是否為空
            if not similar_results['ids'] or len(similar_results['ids']) == 0:
                continue
            if not similar_results['ids'][0] or len(similar_results['ids'][0]) == 0:
                continue

            # 處理每個相似卡片
            for j, similar_id in enumerate(similar_results['ids'][0]):
                # 跳過自己
                if similar_id == card_id:
                    continue

                # 避免重複處理
                pair = tuple(sorted([card_id, similar_id]))
                if pair in processed_pairs:
                    continue
                processed_pairs.add(pair)

                # 獲取相似度
                similarity = 1.0 - similar_results['distances'][0][j]  # ChromaDB 返回距離
                if similarity < min_similarity:
                    continue

                # 找到對應的卡片數據
                similar_card = next((c for c in cards if c['zettel_id'] == similar_id), None)
                if not similar_card:
                    continue

                # 判定關係類型
                relation_type = self._classify_relation_type(
                    card, similar_card, similarity
                )

                # 過濾關係類型
                if relation_types and relation_type not in relation_types:
                    continue

                # 計算信度
                confidence = self._calculate_confidence(
                    card, similar_card, similarity, relation_type
                )

                # 獲取共同概念
                shared_concepts = self._extract_shared_concepts_from_cards(card, similar_card)

                # 創建關係
                relation = ConceptRelation(
                    card_id_1=card_id,
                    card_id_2=similar_id,
                    card_title_1=card['title'],
                    card_title_2=similar_card['title'],
                    relation_type=relation_type,
                    confidence_score=confidence,
                    semantic_similarity=similarity,
                    link_explicit=self._check_explicit_link(card, similar_id),
                    shared_concepts=shared_concepts,
                    paper_ids=[card['paper_id'], similar_card['paper_id']]
                )
                relations.append(relation)

        print(f"\n[3] 識別完成")
        print(f"   總關係數: {len(relations)}")

        # 按信度排序
        relations = sorted(relations, key=lambda r: r.confidence_score, reverse=True)

        # 統計關係類型分布
        type_counts = defaultdict(int)
        for r in relations:
            type_counts[r.relation_type] += 1

        print(f"\n[4] 關係類型分布:")
        for rel_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {rel_type:20} : {count:4} 個")

        print("="*70 + "\n")

        return relations

    def _classify_relation_type(
        self,
        card1: Dict,
        card2: Dict,
        similarity: float
    ) -> str:
        """判定兩張卡片間的關係類型

        判定邏輯:
        1. 檢查明確連結方向（→ 或 ←）
        2. 檢查內容中的關係關鍵詞
        3. 根據相似度判定一般相關性

        參數:
            card1: 第一張卡片數據
            card2: 第二張卡片數據
            similarity: 向量相似度

        返回:
            str: 關係類型
        """
        content1 = card1.get('content', '').lower()
        content2 = card2.get('content', '').lower()
        card2_id = card2.get('zettel_id', '')

        # 1. 檢查 card1 中是否有指向 card2 的明確連結
        # 格式: [[card2_id]] 或 --leads_to--> card2_id
        if f'[[{card2_id}]]' in card1.get('content', ''):
            # 檢查連結周圍的上下文
            if '-->' in content1 or '導向' in content1 or 'leads to' in content1:
                return 'leads_to'
            elif '<--' in content1 or '基於' in content1 or 'based on' in content1:
                return 'based_on'

        # 2. 檢查對比關係關鍵詞
        contrast_keywords = ['但', '然而', '相反', '對比', 'however', 'but', 'contrast', 'differ']
        if any(kw in content1 or kw in content2 for kw in contrast_keywords):
            return 'contrasts_with'

        # 3. 檢查上下位關係
        superclass_keywords = ['包含', '抽象', '泛指', 'include', 'general', 'abstract', 'superclass']
        subclass_keywords = ['具體', '特例', '實例', 'specific', 'instance', 'example', 'subclass']

        if any(kw in content1 for kw in superclass_keywords):
            return 'superclass_of'
        if any(kw in content1 for kw in subclass_keywords):
            return 'subclass_of'

        # 4. 根據相似度判定
        if similarity >= 0.7:
            # 高相似度，可能是相關概念
            return 'related_to'
        elif similarity >= 0.5:
            # 中等相似度
            # 檢查是否有方向性關鍵詞
            directional_keywords = ['因此', '所以', '導致', 'therefore', 'thus', 'result']
            if any(kw in content1 for kw in directional_keywords):
                return 'leads_to'
            return 'related_to'
        else:
            # 低相似度，默認為一般相關
            return 'related_to'

    def _calculate_confidence(
        self,
        card1: Dict,
        card2: Dict,
        similarity: float,
        relation_type: str
    ) -> float:
        """計算關係的信度評分（多維度）

        評分維度:
        - semantic_similarity (40%): 向量相似度
        - link_explicit (30%): 明確連結存在
        - co_occurrence (20%): 共同概念數量
        - domain_consistency (10%): 領域一致性

        參數:
            card1, card2: 卡片數據
            similarity: 向量相似度
            relation_type: 關係類型

        返回:
            float: 信度評分 (0.0-1.0)
        """
        scores = {}

        # 1. 語義相似度 (40%)
        scores['semantic_similarity'] = similarity * 0.4

        # 2. 明確連結 (30%) - Phase 2.3 改進: 使用多層次連結檢測
        link_strength = self._check_explicit_link_enhanced(card1, card2.get('zettel_id', ''))
        # link_strength 範圍 0.0-1.0，映射到 30% 權重
        scores['link_explicit'] = link_strength * 0.3

        # 3. 共同概念 (20%) - Phase 2.3 改進: 使用加權評分
        shared_concepts, weighted_similarity = self._extract_shared_concepts_enhanced(card1, card2)
        # 使用加權相似度（已正規化到 0-1）
        scores['co_occurrence'] = weighted_similarity * 0.2

        # 4. 領域一致性 (10%) - Phase 2.3 改進: 使用領域相似度矩陣
        domain1_str = card1.get('domain', '')
        domain2_str = card2.get('domain', '')
        domains1 = self._parse_domain(domain1_str)
        domains2 = self._parse_domain(domain2_str)
        domain_similarity = self._calculate_multi_domain_similarity(domains1, domains2)
        # 將相似度映射到 0.03-0.10 範圍（保留原始權重 10%）
        scores['domain_consistency'] = domain_similarity * 0.10

        # 總分
        total_score = sum(scores.values())

        return round(total_score, 3)

    def _check_explicit_link(self, card: Dict, target_id: str) -> bool:
        """檢查卡片中是否有指向目標卡片的明確連結

        參數:
            card: 卡片數據
            target_id: 目標卡片 ID

        返回:
            bool: 是否有明確連結
        """
        # 優先使用 ai_notes（Plan B），如果為 NULL 則 fallback 到從 content 提取
        ai_notes = card.get('ai_notes')
        if ai_notes:
            # ai_notes 已經是純 AI 內容，直接使用
            ai_content = ai_notes
        else:
            # Fallback: 從 content 提取 AI 內容（過濾人類筆記）
            content = card.get('content', '')
            ai_content = extract_ai_content(content)

        # 檢查 Obsidian 格式的連結: [[target_id]]
        return f'[[{target_id}]]' in ai_content

    def _extract_section(self, content: str, section_name: str) -> str:
        """從 Markdown 內容中提取特定區段

        參數:
            content: Markdown 內容
            section_name: 區段名稱（例如 "連結網絡"、"來源脈絡"、"個人筆記"）

        返回:
            str: 區段內容，如果不存在則返回空字串
        """
        if not content:
            return ""

        # 構建區段標題的正則表達式（支援不同層級的標題）
        # 例如：## 連結網絡、### 連結網絡
        pattern = rf'^#+\s*{re.escape(section_name)}.*?$'

        # 尋找區段開始位置
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if not match:
            return ""

        # 提取從區段開始到下一個同級或更高級標題之間的內容
        start_pos = match.end()

        # 確定當前標題的層級（#的數量）
        current_level = len(re.match(r'^#+', match.group()).group())

        # 尋找下一個同級或更高級的標題
        next_header_pattern = rf'^#{{{1},{current_level}}}(?!#)\s+'
        remaining_content = content[start_pos:]
        next_match = re.search(next_header_pattern, remaining_content, re.MULTILINE)

        if next_match:
            section_content = remaining_content[:next_match.start()]
        else:
            section_content = remaining_content

        return section_content.strip()

    def _extract_link_context(self, content: str, target_id: str, context_window: int = 50) -> str:
        """提取連結周圍的語境

        參數:
            content: 文本內容
            target_id: 目標卡片 ID
            context_window: 上下文窗口大小（字元數）

        返回:
            str: 連結周圍的上下文，如果沒有連結則返回空字串
        """
        link_pattern = re.escape(f'[[{target_id}]]')
        match = re.search(link_pattern, content)

        if not match:
            return ""

        # 提取連結位置前後 context_window 個字元
        start = max(0, match.start() - context_window)
        end = min(len(content), match.end() + context_window)

        context = content[start:end].strip()
        return context

    def _check_explicit_link_enhanced(self, card: Dict, target_id: str) -> float:
        """增強版明確連結檢測（Phase 2.3 改進 1）

        根據連結位置和語境給予不同評分:
        - [AI Agent] 區段（帶語境）: 0.5-1.0（深度關聯）
        - "## 連結網絡" 區段: 0.6-0.8（結構化關聯）
        - "## 來源脈絡" 區段: 0.4（脈絡關聯）
        - 其他區段（說明、標題）: 0.3（弱關聯）

        參數:
            card: 卡片數據
            target_id: 目標卡片 ID

        返回:
            float: 連結強度評分 (0.0-1.0)，映射到 link_explicit 維度的貢獻
        """
        content = card.get('content', '')
        if not content:
            return 0.0

        link_text = f'[[{target_id}]]'
        if link_text not in content:
            return 0.0

        # 初始化最高分數
        max_score = 0.0

        # 1. 檢查 [AI Agent] 區段（在"## 個人筆記"內）
        personal_notes = self._extract_section(content, '個人筆記')
        if personal_notes:
            # 提取 [AI Agent] 區段
            ai_agent_pattern = r'\*\*\[AI Agent\]\*\*:\s*(.+?)(?=\*\*\[Human\]\*\*:|##|$)'
            ai_agent_match = re.search(ai_agent_pattern, personal_notes, re.DOTALL)

            if ai_agent_match and link_text in ai_agent_match.group(1):
                # 提取連結語境
                context = self._extract_link_context(ai_agent_match.group(1), target_id, context_window=50)

                # 分析語境中的關係詞
                relation_keywords = {
                    'strong': ['基於', '來自', '延伸', '發展', '建立在', 'based on', 'derived from', 'extends'],
                    'directional': ['導向', '指向', '通往', 'leads to', 'points to'],
                    'critical': ['對比', '挑戰', '質疑', 'contrasts', 'challenges', 'questions'],
                    'related': ['相關', '連結', '關聯', 'related', 'connected', 'linked']
                }

                # 根據語境詞彙給分
                context_lower = context.lower()
                if any(kw in context_lower for kw in relation_keywords['strong']):
                    max_score = max(max_score, 1.0)  # 強關係
                elif any(kw in context_lower for kw in relation_keywords['directional']):
                    max_score = max(max_score, 0.8)  # 方向性關係
                elif any(kw in context_lower for kw in relation_keywords['critical']):
                    max_score = max(max_score, 0.7)  # 批判性關係
                elif any(kw in context_lower for kw in relation_keywords['related']):
                    max_score = max(max_score, 0.6)  # 一般相關
                else:
                    max_score = max(max_score, 0.5)  # AI Agent 區段但無明顯關係詞

        # 2. 檢查"## 連結網絡"區段
        link_network = self._extract_section(content, '連結網絡')
        if link_network and link_text in link_network:
            # 檢查是否有結構化的連結語義
            context = self._extract_link_context(link_network, target_id, context_window=30)

            # 識別連結語義類型
            if any(marker in context for marker in ['基於 ->', '來自 ->']):
                max_score = max(max_score, 0.8)  # 明確的基礎關係
            elif any(marker in context for marker in ['導向 ->', '延伸 ->']):
                max_score = max(max_score, 0.75)  # 明確的延伸關係
            elif any(marker in context for marker in ['相關 <->', '對比 <->']):
                max_score = max(max_score, 0.7)  # 明確的雙向關係
            else:
                max_score = max(max_score, 0.6)  # 連結網絡中但無特定語義

        # 3. 檢查"## 來源脈絡"區段（future: prompt 改進）
        source_context = self._extract_section(content, '來源脈絡')
        if source_context and link_text in source_context:
            max_score = max(max_score, 0.4)  # 脈絡關聯（較弱）

        # 4. 檢查其他區段（說明、標題等）
        if max_score == 0.0 and link_text in content:
            # 在其他區段中找到連結
            max_score = 0.3  # 弱關聯

        return max_score

    def _extract_shared_concepts_from_cards(self, card1: Dict, card2: Dict) -> List[str]:
        """提取兩張卡片的共同概念

        從以下來源提取概念:
        - tags (標籤)
        - core_concept (核心概念中的關鍵詞)
        - title (標題中的關鍵詞)

        參數:
            card1, card2: 卡片數據

        返回:
            List[str]: 共同概念列表
        """
        def extract_concepts(card: Dict) -> Set[str]:
            concepts = set()

            # 1. 從標籤提取
            tags = card.get('tags', '')
            if tags:
                try:
                    if isinstance(tags, str):
                        if tags.startswith('['):
                            tag_list = json.loads(tags)
                        else:
                            tag_list = [t.strip() for t in tags.split(',')]
                        concepts.update(tag_list)
                    elif isinstance(tags, list):
                        concepts.update(tags)
                except:
                    pass

            # 2. 從核心概念提取關鍵詞
            core = card.get('core_concept', '')
            if core:
                # 簡單分詞: 移除標點，按空格分割
                words = re.findall(r'\w+', core.lower())
                # 只保留長度 >= 3 的詞（過濾停用詞）
                keywords = [w for w in words if len(w) >= 3]
                concepts.update(keywords)

            # 3. 從標題提取關鍵詞
            title = card.get('title', '')
            if title:
                words = re.findall(r'\w+', title.lower())
                keywords = [w for w in words if len(w) >= 3]
                concepts.update(keywords)

            return concepts

        concepts1 = extract_concepts(card1)
        concepts2 = extract_concepts(card2)

        # 計算交集
        shared = concepts1 & concepts2

        return sorted(list(shared))

    def _extract_chinese_keywords(self, text: str, top_n: int = 10) -> Set[str]:
        """提取中文關鍵詞

        使用預定義詞典 + 正則表達式提取常見學術詞彙
        如果安裝了 jieba，則使用 jieba 分詞作為補充

        參數:
            text: 要提取關鍵詞的文本
            top_n: 返回前 N 個關鍵詞

        返回:
            Set[str]: 關鍵詞集合
        """
        if not text:
            return set()

        keywords = set()

        # 1. 預定義學術詞典（認知科學、語言學、AI 常用術語）
        predefined_patterns = [
            # 認知科學
            r'(工作記憶|長期記憶|短期記憶|語義記憶|情節記憶)',
            r'(注意力|選擇性注意|分散注意|注意機制)',
            r'(心理表徵|心智模型|認知負荷|認知架構)',
            r'(視覺處理|聽覺處理|多感官整合)',
            r'(執行功能|抑制控制|工作記憶更新|認知彈性)',

            # 語言學
            r'(語法|句法|語義|語用|音韻|詞彙)',
            r'(名詞|動詞|形容詞|副詞|量詞|分類詞)',
            r'(語言習得|第二語言|母語|雙語)',
            r'(語言演化|語言變化|語言接觸)',

            # AI/機器學習
            r'(深度學習|機器學習|神經網絡|卷積|循環神經)',
            r'(自然語言處理|語言模型|詞向量|注意力機制)',
            r'(監督學習|非監督學習|強化學習)',
            r'(特徵提取|特徵工程|降維)',

            # 研究方法
            r'(實驗設計|對照組|實驗組|隨機分配)',
            r'(量化研究|質性研究|混合方法)',
            r'(信度|效度|內部一致性|建構效度)',
            r'(統計檢定|顯著性|效果量)',

            # 通用學術詞彙
            r'(理論|模型|假設|預測|驗證)',
            r'(數據|結果|發現|證據)',
            r'(方法|程序|材料|參與者)',
        ]

        # 使用預定義模式提取
        for pattern in predefined_patterns:
            matches = re.findall(pattern, text)
            keywords.update(matches)

        # 2. 提取 2-4 個連續中文字符的詞組
        chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        keywords.update(chinese_words[:top_n * 2])  # 取前 2*top_n 個候選

        # 3. 如果有 jieba，使用 jieba 分詞補充（可選）
        try:
            import jieba
            jieba.setLogLevel(jieba.logging.INFO)  # 抑制 jieba 日誌
            seg_list = jieba.cut(text)
            for word in seg_list:
                if len(word) >= 2 and re.search(r'[\u4e00-\u9fa5]', word):
                    keywords.add(word)
        except ImportError:
            pass  # jieba 未安裝，跳過

        # 4. 過濾停用詞和過短詞
        stopwords = {'的', '了', '在', '是', '和', '與', '或', '但', '等',
                     '因此', '所以', '如果', '雖然', '但是', '然而', '以及',
                     '這個', '那個', '我們', '他們', '可以', '應該', '能夠'}
        keywords = {w for w in keywords if len(w) >= 2 and w not in stopwords}

        return keywords

    def _extract_concepts_enhanced(self, card: Dict) -> Dict[str, float]:
        """增強版概念提取（Phase 2.3 改進）

        從 5 個來源提取概念，並給予不同權重:
        - tags (1.0): 最準確
        - core_concept (0.9): 次準確
        - description (0.8): 首段說明
        - title (0.7): 較簡短
        - ai_notes (0.6): 較發散

        參數:
            card: 卡片數據

        返回:
            Dict[str, float]: 概念 -> 權重分數
        """
        concepts = {}  # concept -> weight

        # 1. 從 tags 提取（權重 1.0）
        tags = card.get('tags', '')
        if tags:
            try:
                if isinstance(tags, str):
                    if tags.startswith('['):
                        tag_list = json.loads(tags)
                    else:
                        tag_list = [t.strip() for t in tags.split(',')]
                elif isinstance(tags, list):
                    tag_list = tags
                else:
                    tag_list = []

                for tag in tag_list:
                    tag = tag.strip().lower()
                    if tag:
                        concepts[tag] = max(concepts.get(tag, 0), 1.0)
            except:
                pass

        # 2. 從 core_concept 提取（權重 0.9）
        core = card.get('core_concept', '')
        if core:
            # 使用增強的中文分詞
            keywords = self._extract_chinese_keywords(core, top_n=5)
            for word in keywords:
                word = word.lower()
                concepts[word] = max(concepts.get(word, 0), 0.9)

            # 英文關鍵詞（正則表達式）
            english_words = re.findall(r'\b[a-z]{3,}\b', core.lower())
            for word in english_words:
                concepts[word] = max(concepts.get(word, 0), 0.9)

        # 3. 從 description 提取（權重 0.8）- 新增！
        description = card.get('description', '')
        if description:
            keywords = self._extract_chinese_keywords(description, top_n=8)
            for word in keywords:
                word = word.lower()
                concepts[word] = max(concepts.get(word, 0), 0.8)

            english_words = re.findall(r'\b[a-z]{3,}\b', description.lower())
            for word in english_words[:10]:  # 限制英文詞數
                concepts[word] = max(concepts.get(word, 0), 0.8)

        # 4. 從 title 提取（權重 0.7）
        title = card.get('title', '')
        if title:
            keywords = self._extract_chinese_keywords(title, top_n=5)
            for word in keywords:
                word = word.lower()
                concepts[word] = max(concepts.get(word, 0), 0.7)

            english_words = re.findall(r'\b[a-z]{3,}\b', title.lower())
            for word in english_words:
                concepts[word] = max(concepts.get(word, 0), 0.7)

        # 5. 從 ai_notes 提取（權重 0.6）- 新增！
        ai_notes = card.get('ai_notes', '')
        if ai_notes:
            keywords = self._extract_chinese_keywords(ai_notes, top_n=10)
            for word in keywords:
                word = word.lower()
                concepts[word] = max(concepts.get(word, 0), 0.6)

            english_words = re.findall(r'\b[a-z]{3,}\b', ai_notes.lower())
            for word in english_words[:15]:  # 限制英文詞數
                concepts[word] = max(concepts.get(word, 0), 0.6)

        return concepts

    def _extract_shared_concepts_enhanced(self, card1: Dict, card2: Dict) -> Tuple[List[str], float]:
        """增強版共同概念提取（Phase 2.3 改進）

        使用加權評分機制計算共同概念相似度

        參數:
            card1, card2: 卡片數據

        返回:
            Tuple[List[str], float]: (共同概念列表, 加權相似度分數)
        """
        concepts1 = self._extract_concepts_enhanced(card1)
        concepts2 = self._extract_concepts_enhanced(card2)

        # 找出共同概念
        shared_concepts = set(concepts1.keys()) & set(concepts2.keys())

        if not shared_concepts:
            return [], 0.0

        # 計算加權相似度
        # 使用兩張卡片中較低的權重（保守估計）
        weighted_score = sum(
            min(concepts1[concept], concepts2[concept])
            for concept in shared_concepts
        )

        # 正規化：除以兩張卡片的概念總權重的平均值
        total_weight1 = sum(concepts1.values()) or 1.0
        total_weight2 = sum(concepts2.values()) or 1.0
        avg_total = (total_weight1 + total_weight2) / 2

        normalized_score = min(weighted_score / avg_total, 1.0)

        return sorted(list(shared_concepts)), normalized_score

    def _parse_domain(self, domain_str: str) -> List[str]:
        """解析領域字串（支援多領域）

        範例:
        - "CogSci" -> ["CogSci"]
        - "CogSci, AI" -> ["CogSci", "AI"]
        - "CogSci,Linguistics" -> ["CogSci", "Linguistics"]

        參數:
            domain_str: 領域字串

        返回:
            List[str]: 領域列表
        """
        if not domain_str:
            return []

        # 分割並清理空白
        domains = [d.strip() for d in domain_str.split(',')]
        return [d for d in domains if d]

    def _get_domain_similarity(self, domain1: str, domain2: str) -> float:
        """查詢兩個領域的相似度

        參數:
            domain1, domain2: 領域代碼

        返回:
            float: 相似度分數 (0.0-1.0)
        """
        if not domain1 or not domain2:
            return DEFAULT_DOMAIN_SIMILARITY

        # 相同領域
        if domain1 == domain2:
            return 1.0

        # 查詢矩陣（順序無關）
        key1 = (domain1, domain2)
        key2 = (domain2, domain1)

        if key1 in DOMAIN_SIMILARITY_MATRIX:
            return DOMAIN_SIMILARITY_MATRIX[key1]
        elif key2 in DOMAIN_SIMILARITY_MATRIX:
            return DOMAIN_SIMILARITY_MATRIX[key2]
        else:
            return DEFAULT_DOMAIN_SIMILARITY

    def _calculate_multi_domain_similarity(self, domains1: List[str], domains2: List[str]) -> float:
        """計算多領域相似度（Phase 2.3 改進）

        使用最大相似度策略：
        找出所有領域對中相似度最高的組合

        範例:
        - card1: ["CogSci", "AI"]
        - card2: ["Linguistics"]
        - 計算: max(
            similarity(CogSci, Linguistics),
            similarity(AI, Linguistics)
          )

        參數:
            domains1, domains2: 領域列表

        返回:
            float: 相似度分數 (0.0-1.0)
        """
        if not domains1 or not domains2:
            return DEFAULT_DOMAIN_SIMILARITY

        # 計算所有領域對的相似度，取最大值
        max_similarity = 0.0
        for d1 in domains1:
            for d2 in domains2:
                similarity = self._get_domain_similarity(d1, d2)
                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def build_concept_network(
        self,
        min_similarity: float = 0.4,
        relation_types: Optional[List[str]] = None,
        min_confidence: float = 0.3
    ) -> Dict:
        """建構 Zettelkasten 概念網絡 (Phase 2.1)

        參數:
            min_similarity: 最小語義相似度閾值
            relation_types: 要包含的關係類型
            min_confidence: 最小信度閾值

        返回:
            Dict: 包含 nodes, edges, statistics 的網絡數據
        """
        print("\n" + "="*70)
        print("[Phase 2.1] 建構 Zettelkasten 概念網絡")
        print("="*70)

        # 1. 識別所有關係
        print("\n[1] 識別概念關係...")
        relations = self.find_concept_relations(
            min_similarity=min_similarity,
            relation_types=relation_types
        )

        # 過濾低信度關係
        relations = [r for r in relations if r.confidence_score >= min_confidence]
        print(f"   過濾後關係數: {len(relations)} (信度 >= {min_confidence})")

        # 2. 建構節點列表
        print("\n[2] 建構節點...")
        node_dict = {}  # card_id -> node data
        for relation in relations:
            # 添加 card1
            if relation.card_id_1 not in node_dict:
                node_dict[relation.card_id_1] = {
                    'card_id': relation.card_id_1,
                    'title': relation.card_title_1,
                    'degree': 0,  # 度（連接數）
                    'in_degree': 0,
                    'out_degree': 0,
                    'paper_ids': []
                }
            # 添加 card2
            if relation.card_id_2 not in node_dict:
                node_dict[relation.card_id_2] = {
                    'card_id': relation.card_id_2,
                    'title': relation.card_title_2,
                    'degree': 0,
                    'in_degree': 0,
                    'out_degree': 0,
                    'paper_ids': []
                }

            # 更新度統計
            node_dict[relation.card_id_1]['degree'] += 1
            node_dict[relation.card_id_2]['degree'] += 1

            # 根據關係類型更新有向度
            if relation.relation_type == 'leads_to':
                node_dict[relation.card_id_1]['out_degree'] += 1
                node_dict[relation.card_id_2]['in_degree'] += 1
            elif relation.relation_type == 'based_on':
                node_dict[relation.card_id_1]['in_degree'] += 1
                node_dict[relation.card_id_2]['out_degree'] += 1
            else:
                # 對稱關係
                node_dict[relation.card_id_1]['out_degree'] += 1
                node_dict[relation.card_id_1]['in_degree'] += 1
                node_dict[relation.card_id_2]['out_degree'] += 1
                node_dict[relation.card_id_2]['in_degree'] += 1

            # 添加關聯論文
            for paper_id in relation.paper_ids:
                if paper_id not in node_dict[relation.card_id_1]['paper_ids']:
                    node_dict[relation.card_id_1]['paper_ids'].append(paper_id)
                if paper_id not in node_dict[relation.card_id_2]['paper_ids']:
                    node_dict[relation.card_id_2]['paper_ids'].append(paper_id)

        nodes = list(node_dict.values())
        print(f"   節點數: {len(nodes)}")

        # 3. 建構邊列表
        print("\n[3] 建構邊...")
        edges = []
        for relation in relations:
            edge = {
                'source': relation.card_id_1,
                'target': relation.card_id_2,
                'relation_type': relation.relation_type,
                'confidence': relation.confidence_score,
                'similarity': relation.semantic_similarity,
                'explicit_link': relation.link_explicit,
                'shared_concepts': relation.shared_concepts
            }
            edges.append(edge)
        print(f"   邊數: {len(edges)}")

        # 4. 計算網絡統計
        print("\n[4] 計算網絡統計...")
        statistics = self._calculate_network_statistics(nodes, edges, relations)

        # 5. 識別核心節點（高度節點）
        hub_nodes = sorted(nodes, key=lambda n: n['degree'], reverse=True)[:10]

        network = {
            'nodes': nodes,
            'edges': edges,
            'statistics': statistics,
            'hub_nodes': hub_nodes,
            'relations': edges  # 使用 edges（已包含所有關係數據，且格式正確：source/target）
        }

        print("\n[5] 網絡統計摘要:")
        print(f"   節點數: {statistics['node_count']}")
        print(f"   邊數: {statistics['edge_count']}")
        print(f"   平均度: {statistics['avg_degree']:.2f}")
        print(f"   最大度: {statistics['max_degree']}")
        print(f"   網絡密度: {statistics['density']:.4f}")
        print(f"\n[6] Top 5 核心節點 (Hub Nodes):")
        for i, node in enumerate(hub_nodes[:5], 1):
            print(f"   {i}. {node['card_id']:30} | 度: {node['degree']:3} | {node['title'][:40]}")

        print("="*70 + "\n")

        return network

    def _calculate_network_statistics(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        relations: List[ConceptRelation]
    ) -> Dict:
        """計算網絡統計指標

        參數:
            nodes: 節點列表
            edges: 邊列表
            relations: 關係列表

        返回:
            Dict: 統計指標
        """
        node_count = len(nodes)
        edge_count = len(edges)

        if node_count == 0:
            return {
                'node_count': 0,
                'edge_count': 0,
                'avg_degree': 0,
                'max_degree': 0,
                'min_degree': 0,
                'density': 0,
                'avg_confidence': 0,
                'avg_similarity': 0
            }

        # 度統計
        degrees = [n['degree'] for n in nodes]
        avg_degree = sum(degrees) / len(degrees)
        max_degree = max(degrees)
        min_degree = min(degrees)

        # 網絡密度 = 實際邊數 / 可能最大邊數
        max_edges = node_count * (node_count - 1) / 2  # 無向圖
        density = edge_count / max_edges if max_edges > 0 else 0

        # 關係質量統計
        avg_confidence = sum(r.confidence_score for r in relations) / len(relations) if relations else 0
        avg_similarity = sum(r.semantic_similarity for r in relations) / len(relations) if relations else 0

        # 關係類型統計
        type_counts = defaultdict(int)
        for r in relations:
            type_counts[r.relation_type] += 1

        return {
            'node_count': node_count,
            'edge_count': edge_count,
            'avg_degree': round(avg_degree, 2),
            'max_degree': max_degree,
            'min_degree': min_degree,
            'density': round(density, 4),
            'avg_confidence': round(avg_confidence, 3),
            'avg_similarity': round(avg_similarity, 3),
            'relation_type_counts': dict(type_counts)
        }

    # ========== 6. 統計和報告 ==========

    def generate_report(self, output_dir: str = "output/relations") -> Dict:
        """生成完整的關係分析報告"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        papers = self._get_papers_safe()
        total_papers = len(papers)

        print(f"\n{'='*70}")
        print(f"Relation-Finder - Relationship Analysis")
        print(f"{'='*70}")
        print(f"Total Papers: {total_papers}")

        # 1. Citation Relationship Analysis
        print(f"\n[1] Analyzing title similarity citations...")
        citations = self.find_citations_by_title_similarity()
        print(f"    Found {len(citations)} similar citations")

        citations_mermaid = self.export_citations_to_mermaid(citations)
        with open(output_path / "citations_network.md", 'w', encoding='utf-8') as f:
            f.write("# Paper Citation Network\n\n")
            f.write(citations_mermaid)

        citations_json = [asdict(c) for c in citations]
        with open(output_path / "citations.json", 'w', encoding='utf-8') as f:
            json.dump(citations_json, f, ensure_ascii=False, indent=2)

        # 2. Co-Author Network Analysis
        print(f"\n[2] Analyzing co-author network...")
        author_papers, coauthor_edges = self.find_co_authors()
        total_authors = len(author_papers)
        print(f"    Found {total_authors} authors, {len(coauthor_edges)} co-author pairs")

        coauthor_mermaid = self.export_coauthors_to_mermaid(author_papers, coauthor_edges)
        with open(output_path / "coauthor_network.md", 'w', encoding='utf-8') as f:
            f.write("# Co-Author Network\n\n")
            f.write(coauthor_mermaid)

        coauthor_json = [asdict(e) for e in coauthor_edges]
        with open(output_path / "coauthors.json", 'w', encoding='utf-8') as f:
            json.dump(coauthor_json, f, ensure_ascii=False, indent=2)

        # 3. Paper Concept Co-Occurrence Analysis
        print(f"\n[3] Analyzing paper concept co-occurrence...")
        concept_pairs = self.find_co_occurrence(top_k=30)
        all_concepts = set()
        for pair in concept_pairs:
            all_concepts.add(pair.concept1)
            all_concepts.add(pair.concept2)
        print(f"    Found {len(all_concepts)} concepts, {len(concept_pairs)} co-occurrences")

        concept_mermaid = self.export_concepts_to_mermaid(concept_pairs)
        with open(output_path / "paper_concept_network.md", 'w', encoding='utf-8') as f:
            f.write("# Paper Concept Co-Occurrence Network\n\n")
            f.write(concept_mermaid)

        concept_json = [asdict(p) for p in concept_pairs]
        with open(output_path / "paper_concepts.json", 'w', encoding='utf-8') as f:
            json.dump(concept_json, f, ensure_ascii=False, indent=2)

        # 4. Zettelkasten Concept Analysis (NEW!)
        print(f"\n[4] Analyzing zettelkasten concepts...")
        zettel_summary = self.zettel_analyzer.generate_report(output_dir=output_dir)
        zettel_concepts_total = zettel_summary['total_unique_concepts']
        zettel_relations = zettel_summary['concept_relations']
        print(f"    Found {zettel_concepts_total} zettel concepts, {zettel_relations} relations")

        # 5. Generate Summary Report
        summary = {
            'total_papers': total_papers,
            'total_authors': total_authors,
            'paper_concepts': len(all_concepts),
            'paper_concept_pairs': len(concept_pairs),
            'zettel_concepts': zettel_concepts_total,
            'zettel_concept_relations': zettel_relations,
            'citations': len(citations),
            'coauthors': len(coauthor_edges),
        }

        print(f"\n{'='*70}")
        print(f"Complete Analysis Summary")
        print(f"{'='*70}")
        print(f"Papers: {summary['total_papers']}")
        print(f"Authors: {summary['total_authors']}")
        print(f"Paper concepts: {summary['paper_concepts']}")
        print(f"Zettel concepts: {summary['zettel_concepts']} (UNIQUE)")
        print(f"Zettel concept relations: {summary['zettel_concept_relations']}")
        print(f"Co-author pairs: {summary['coauthors']}")
        print(f"Citations: {summary['citations']}")
        print(f"\nAll reports saved to: {output_path}")
        print(f"{'='*70}\n")

        return summary


class ZettelLinker:
    """Phase 2.5: Zettelkasten 卡片與論文的自動關聯系統"""

    def __init__(self, db_path: str = "knowledge_base/index.db"):
        self.db_path = db_path
        self.conn = None
        self.stats = {
            'total_zettel_folders': 0,
            'total_cards': 0,
            'linked_cards': 0,
            'failed_links': 0,
        }
        self.failed_links = []

    def connect(self):
        """連接資料庫"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()

    def extract_cite_key_from_card_id(self, card_id: str, folder_name: str = None) -> Optional[str]:
        """從卡片 ID 提取 cite_key - 新標準格式 (版本後綴支援)

        支援的卡片ID格式:
          - 標準格式: Author-Year-Number (e.g., Wu-2020-001)
          - 版本後綴: Author-Year[a-z]-Number (e.g., Her-2012a-001)

        參數:
          card_id: 卡片檔名 (含或不含 .md 後綴)
          folder_name: 資料夾名稱 (已不使用，保留用於向後相容)

        返回:
          cite_key: 如 "Wu-2020" 或 "Her-2012a" (含版本後綴)
          None: 如果 card_id 格式無效
        """
        card_id = card_id.replace('.md', '')

        # 新標準格式: Author-Year[suffix]-Number
        # 支援: Wu-2020-001 (標準) 和 Chen-2023c-001 (版本後綴)
        match = re.match(r'^([A-Za-z]+-\d+(?:[a-z])?)-\d{3}$', card_id)
        if match:
            return match.group(1)

        return None

    def _extract_cite_key_from_folder(self, folder_name: str) -> Optional[str]:
        """從資料夾名稱提取 cite_key (用於 domain 欄位，非舊格式相容)

        新標準格式卡片 (Author-Year-Number) 的 cite_key 直接從檔名提取。
        此方法用於提取資料夾中的 domain 資訊，用於資料庫記錄。

        示例:
          zettel_Wu-2020_20251104 -> Wu-2020
          zettel_Her-2012a_20251104 -> Her-2012a
        """
        if folder_name.startswith('zettel_'):
            content = folder_name[7:]
        else:
            content = folder_name

        # 移除時間戳 (_YYYYMMDD)
        match = re.match(r'^(.+)_\d{8}$', content)
        if match:
            return match.group(1)

        return content

    def get_paper_by_cite_key(self, cite_key: str) -> Optional[Dict]:
        """從資料庫查找論文"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, cite_key, title FROM papers WHERE cite_key = ?",
            (cite_key,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def scan_zettel_folders(self, zettel_base: str = "output/zettelkasten_notes") -> List[Tuple[Path, str, str]]:
        """掃描所有 Zettel 資料夾"""
        zettel_path = Path(zettel_base)
        folders = sorted([d for d in zettel_path.iterdir() if d.is_dir() and d.name.startswith('zettel_')])

        self.stats['total_zettel_folders'] = len(folders)
        cards = []

        for folder in folders:
            card_dir = folder / 'zettel_cards'
            if not card_dir.exists():
                continue

            for card_file in sorted(card_dir.glob('*.md')):
                card_id = card_file.stem
                cards.append((card_file, card_id, folder.name))
                self.stats['total_cards'] += 1

        return cards

    def link_zettel_to_papers(self, zettel_base: str = "output/zettelkasten_notes", dry_run: bool = False) -> Dict:
        """自動關聯所有 Zettel 卡片到論文"""
        print("=" * 70)
        print("[PHASE 2.5] Zettelkasten - 論文自動關聯")
        print("=" * 70)

        cards = self.scan_zettel_folders(zettel_base)
        print(f"\n[SCAN] 掃描結果:")
        print(f"   資料夾數: {self.stats['total_zettel_folders']}")
        print(f"   卡片數: {self.stats['total_cards']}")
        print()

        cite_key_groups = defaultdict(list)
        for card_file, card_id, folder_name in cards:
            cite_key = self.extract_cite_key_from_card_id(card_id, folder_name)
            cite_key_groups[cite_key].append((card_file, card_id, folder_name))

        print("[LINKING] 關聯進度:")
        # Sort keys: non-None first, then None
        non_none_keys = sorted([k for k in cite_key_groups.keys() if k is not None])
        none_keys = [k for k in cite_key_groups.keys() if k is None]
        cite_keys = non_none_keys + none_keys

        for cite_key in cite_keys:
            cards_for_key = cite_key_groups[cite_key]

            if cite_key is None:
                print(f"\n[WARN] 無法識別格式 ({len(cards_for_key)} 張卡片):")
                for _, card_id, folder_name in cards_for_key[:3]:
                    print(f"    - {folder_name}/{card_id}")
                self.stats['failed_links'] += len(cards_for_key)
                self.failed_links.extend(cards_for_key)
                continue

            paper = self.get_paper_by_cite_key(cite_key)
            if not paper:
                print(f"\n[ERROR] 論文不存在: {cite_key} ({len(cards_for_key)} 張卡片)")
                self.stats['failed_links'] += len(cards_for_key)
                self.failed_links.extend(cards_for_key)
                continue

            if not dry_run:
                for card_file, card_id, folder_name in cards_for_key:
                    self._add_or_update_zettel_card(paper['id'], card_id, card_file, folder_name)

            print(f"[OK] {cite_key:20} -> Paper {paper['id']:2} | Cards: {len(cards_for_key):3}")
            self.stats['linked_cards'] += len(cards_for_key)

        print("\n" + "=" * 70)
        print("[STATS] 關聯統計:")
        print(f"   成功關聯: {self.stats['linked_cards']} 張")
        print(f"   失敗: {self.stats['failed_links']} 張")
        print(f"   成功率: {100*self.stats['linked_cards']/max(1, self.stats['total_cards']):.1f}%")
        print("=" * 70)

        return self.stats

    def _add_or_update_zettel_card(self, paper_id: int, card_id: str, card_file: Path, folder_name: str = None):
        """添加或更新 Zettel 卡片記錄"""
        cursor = self.conn.cursor()

        with open(card_file, 'r', encoding='utf-8') as f:
            content = f.read()

        card_data = self._parse_card_frontmatter(content)

        # Extract domain from folder name (e.g., "zettel_Ahrens-2016_20251104" -> "Ahrens-2016")
        domain = 'Unknown'
        if folder_name:
            domain = self._extract_cite_key_from_folder(folder_name) or 'Unknown'

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO zettel_cards
                (zettel_id, paper_id, title, content, core_concept, tags, domain,
                 file_path, zettel_folder, card_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                card_id,
                paper_id,
                card_data.get('title', ''),
                content,
                card_data.get('core_concept', card_data.get('summary', '')),
                card_data.get('tags'),
                domain,
                str(card_file),
                folder_name or '',
                card_data.get('type', card_data.get('card_type', 'concept'))
            ))
            self.conn.commit()
        except Exception as e:
            print(f"   [ERROR] 無法添加卡片 {card_id}: {e}")

    def _parse_card_frontmatter(self, content: str) -> Dict:
        """解析 Markdown 卡片的 YAML frontmatter (新標準格式)

        支援的卡片ID格式:
          - 標準格式: Author-Year-Number (e.g., Wu-2020-001)
          - 版本後綴: Author-Year[a-z]-Number (e.g., Her-2012a-001)

        提取的 YAML 欄位:
          - title: 卡片標題
          - summary: 核心概念摘要
          - core_concept: 核心概念
          - tags: 標籤列表
          - type 或 card_type: 卡片類型

        返回:
          Dict: 包含解析的 YAML 欄位
        """
        data = {}
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return data

        yaml_content = match.group(1)

        for line in yaml_content.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()

                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]

                data[key] = value

        # 提取核心概念（從 > **核心**: "..." 格式）
        if not data.get('summary'):
            core_match = re.search(r'> \*\*核心\*\*:\s*"([^"]*)"', content)
            if core_match:
                data['core_concept'] = core_match.group(1)

        # 解析標籤（從 [[tag1], [tag2], ...] 格式）
        if 'tags' not in data or not data['tags']:
            tags_match = re.search(r'tags:\s*(\[\[.*?\]\])', content, re.MULTILINE)
            if tags_match:
                tags_str = tags_match.group(1)
                # 提取 [[tag]] 中的標籤
                tags = re.findall(r'\[\[([^\]]+)\]\]', tags_str)
                data['tags'] = json.dumps(tags) if tags else None

        return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Relation-Finder 關係分析工具")
    parser.add_argument("--kb-path", default="knowledge_base", help="知識庫路徑")
    parser.add_argument("--output", default="output/relations", help="輸出目錄")
    parser.add_argument("--phase2-5", action="store_true", help="執行 Phase 2.5 Zettel 關聯")
    args = parser.parse_args()

    if args.phase2_5:
        # Phase 2.5: Zettel 卡片與論文關聯
        linker = ZettelLinker()
        linker.connect()
        try:
            linker.link_zettel_to_papers(dry_run=False)
        finally:
            linker.close()
    else:
        # 原有功能: 論文間關係分析
        finder = RelationFinder(kb_path=args.kb_path)
        summary = finder.generate_report(output_dir=args.output)
