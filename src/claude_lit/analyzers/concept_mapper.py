#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Concept Mapper 概念網絡視覺化與分析模組 (Phase 2.2)

提供概念網絡的高級分析和互動式視覺化：
- 社群檢測（Community Detection）
- 路徑分析（Path Analysis）
- 中心性分析（Centrality Analysis）
- 互動式網絡圖生成（D3.js / Graphviz）
"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict, deque
from pathlib import Path
import sys
import math

project_root = Path(__file__).parent.parent.parent


from claude_lit.analyzers.relation_finder import RelationFinder


@dataclass
class Community:
    """社群（概念群集）"""
    community_id: int
    nodes: List[str]  # card_id 列表
    size: int
    density: float
    top_concepts: List[str]
    hub_node: str  # 社群中心節點


@dataclass
class ConceptPath:
    """概念推導路徑"""
    start_node: str
    end_node: str
    path: List[str]  # card_id 列表
    length: int
    confidence: float  # 路徑平均信度


@dataclass
class CentralityScores:
    """中心性分數"""
    node_id: str
    degree_centrality: float
    betweenness_centrality: float
    closeness_centrality: float
    pagerank: float


class ConceptNetwork:
    """概念網絡核心類

    封裝網絡數據結構，提供基礎查詢操作
    """

    def __init__(self, network_data: Dict):
        """初始化概念網絡

        參數:
            network_data: RelationFinder.build_concept_network() 的輸出
        """
        self.nodes = network_data.get('nodes', [])
        self.edges = network_data.get('edges', [])
        self.statistics = network_data.get('statistics', {})
        self.hub_nodes = network_data.get('hub_nodes', [])
        self.relations = network_data.get('relations', [])

        # 建立索引結構
        self._build_indices()

    def _build_indices(self):
        """建立索引結構以加速查詢"""
        # 節點索引
        self.node_dict = {node['card_id']: node for node in self.nodes}

        # 鄰接表（無向圖）
        self.adjacency = defaultdict(list)
        for edge in self.edges:
            self.adjacency[edge['source']].append(edge['target'])
            self.adjacency[edge['target']].append(edge['source'])

        # 邊索引（source, target） -> edge
        self.edge_dict = {}
        for edge in self.edges:
            key1 = (edge['source'], edge['target'])
            key2 = (edge['target'], edge['source'])
            self.edge_dict[key1] = edge
            self.edge_dict[key2] = edge  # 對稱

    def get_node(self, card_id: str) -> Optional[Dict]:
        """獲取節點"""
        return self.node_dict.get(card_id)

    def get_neighbors(self, card_id: str) -> List[str]:
        """獲取鄰居節點"""
        return self.adjacency.get(card_id, [])

    def get_edge(self, source: str, target: str) -> Optional[Dict]:
        """獲取邊"""
        return self.edge_dict.get((source, target))

    def node_count(self) -> int:
        """節點數"""
        return len(self.nodes)

    def edge_count(self) -> int:
        """邊數"""
        return len(self.edges)


class CommunityDetector:
    """社群檢測分析器

    使用 Louvain 算法或簡化版本進行社群檢測
    """

    def __init__(self, network: ConceptNetwork):
        self.network = network

    def detect_communities(self, method: str = 'simple') -> List[Community]:
        """檢測社群

        參數:
            method: 'simple' (連通分量) 或 'louvain' (Louvain 算法)

        返回:
            List[Community]: 社群列表
        """
        if method == 'simple':
            return self._detect_by_connected_components()
        elif method == 'louvain':
            return self._detect_by_louvain()
        else:
            raise ValueError(f"Unknown method: {method}")

    def _detect_by_connected_components(self) -> List[Community]:
        """使用連通分量檢測社群（簡單方法）"""
        visited = set()
        communities = []

        for node_id in self.network.node_dict.keys():
            if node_id in visited:
                continue

            # BFS 找連通分量
            component = self._bfs_component(node_id, visited)

            if len(component) > 1:  # 至少 2 個節點才算社群
                community = self._create_community(
                    community_id=len(communities),
                    nodes=component
                )
                communities.append(community)

        return communities

    def _bfs_component(self, start: str, visited: Set[str]) -> List[str]:
        """BFS 尋找連通分量"""
        queue = deque([start])
        visited.add(start)
        component = [start]

        while queue:
            node = queue.popleft()
            for neighbor in self.network.get_neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    component.append(neighbor)

        return component

    def _detect_by_louvain(self) -> List[Community]:
        """使用 Louvain 算法檢測社群（簡化版）

        參考: Blondel et al., 2008
        """
        # 初始化：每個節點一個社群
        node_to_community = {node: i for i, node in enumerate(self.network.node_dict.keys())}

        # 迭代優化
        improved = True
        iteration = 0
        max_iterations = 10

        while improved and iteration < max_iterations:
            improved = False
            iteration += 1

            for node in self.network.node_dict.keys():
                # 計算當前模組度
                current_community = node_to_community[node]
                best_community = current_community
                best_gain = 0.0

                # 嘗試移動到鄰居社群
                neighbor_communities = set()
                for neighbor in self.network.get_neighbors(node):
                    neighbor_communities.add(node_to_community[neighbor])

                for community in neighbor_communities:
                    gain = self._calculate_modularity_gain(
                        node, current_community, community, node_to_community
                    )
                    if gain > best_gain:
                        best_gain = gain
                        best_community = community

                # 移動到最佳社群
                if best_community != current_community:
                    node_to_community[node] = best_community
                    improved = True

        # 構建社群列表
        community_nodes = defaultdict(list)
        for node, comm_id in node_to_community.items():
            community_nodes[comm_id].append(node)

        communities = []
        for comm_id, nodes in community_nodes.items():
            if len(nodes) > 1:
                community = self._create_community(comm_id, nodes)
                communities.append(community)

        return communities

    def _calculate_modularity_gain(
        self,
        node: str,
        from_community: int,
        to_community: int,
        node_to_community: Dict[str, int]
    ) -> float:
        """計算模組度增益（簡化版）"""
        # 計算與目標社群的連接數
        connections_to = 0
        connections_from = 0

        for neighbor in self.network.get_neighbors(node):
            if node_to_community[neighbor] == to_community:
                connections_to += 1
            elif node_to_community[neighbor] == from_community:
                connections_from += 1

        # 簡化的增益計算
        return connections_to - connections_from

    def _create_community(self, community_id: int, nodes: List[str]) -> Community:
        """創建 Community 對象"""
        # 計算社群密度
        internal_edges = 0
        for node in nodes:
            for neighbor in self.network.get_neighbors(node):
                if neighbor in nodes:
                    internal_edges += 1
        internal_edges //= 2  # 無向圖，每條邊計算兩次

        max_edges = len(nodes) * (len(nodes) - 1) / 2
        density = internal_edges / max_edges if max_edges > 0 else 0.0

        # 找出 hub 節點（度最大）
        hub_node = max(nodes, key=lambda n: self.network.node_dict[n]['degree'])

        # 提取 top 概念（從節點標題）
        titles = [self.network.node_dict[n]['title'] for n in nodes]
        top_concepts = titles[:5]  # 簡化：取前 5 個

        return Community(
            community_id=community_id,
            nodes=nodes,
            size=len(nodes),
            density=density,
            top_concepts=top_concepts,
            hub_node=hub_node
        )


class PathAnalyzer:
    """路徑分析器

    分析概念間的推導路徑和傳播路徑
    """

    def __init__(self, network: ConceptNetwork):
        self.network = network

    def find_shortest_path(self, start: str, end: str) -> Optional[ConceptPath]:
        """尋找最短路徑（BFS）"""
        if start not in self.network.node_dict or end not in self.network.node_dict:
            return None

        # BFS
        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            node, path = queue.popleft()

            if node == end:
                # 計算路徑信度
                confidence = self._calculate_path_confidence(path)
                return ConceptPath(
                    start_node=start,
                    end_node=end,
                    path=path,
                    length=len(path) - 1,
                    confidence=confidence
                )

            for neighbor in self.network.get_neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None  # 無路徑

    def find_all_paths(
        self,
        start: str,
        end: str,
        max_length: int = 5
    ) -> List[ConceptPath]:
        """尋找所有路徑（DFS，限制長度）"""
        if start not in self.network.node_dict or end not in self.network.node_dict:
            return []

        all_paths = []
        self._dfs_paths(start, end, [start], all_paths, max_length)

        # 轉換為 ConceptPath 對象
        result = []
        for path in all_paths:
            confidence = self._calculate_path_confidence(path)
            result.append(ConceptPath(
                start_node=start,
                end_node=end,
                path=path,
                length=len(path) - 1,
                confidence=confidence
            ))

        # 按信度排序
        result.sort(key=lambda p: p.confidence, reverse=True)
        return result

    def _dfs_paths(
        self,
        current: str,
        end: str,
        path: List[str],
        all_paths: List[List[str]],
        max_length: int
    ):
        """DFS 尋找所有路徑"""
        if current == end:
            all_paths.append(path.copy())
            return

        if len(path) > max_length:
            return

        for neighbor in self.network.get_neighbors(current):
            if neighbor not in path:  # 避免循環
                path.append(neighbor)
                self._dfs_paths(neighbor, end, path, all_paths, max_length)
                path.pop()

    def _calculate_path_confidence(self, path: List[str]) -> float:
        """計算路徑信度（平均邊信度）"""
        if len(path) < 2:
            return 1.0

        confidences = []
        for i in range(len(path) - 1):
            edge = self.network.get_edge(path[i], path[i+1])
            if edge:
                confidences.append(edge.get('confidence', 0.5))

        return sum(confidences) / len(confidences) if confidences else 0.0

    def find_influential_paths(self, min_length: int = 2) -> List[ConceptPath]:
        """尋找有影響力的路徑（連接 hub 節點）"""
        # 找出 hub 節點
        hubs = sorted(
            self.network.nodes,
            key=lambda n: n['degree'],
            reverse=True
        )[:10]

        influential_paths = []

        # hub 之間的路徑
        for i, hub1 in enumerate(hubs):
            for hub2 in hubs[i+1:]:
                path = self.find_shortest_path(hub1['card_id'], hub2['card_id'])
                if path and path.length >= min_length:
                    influential_paths.append(path)

        # 按信度排序
        influential_paths.sort(key=lambda p: p.confidence, reverse=True)
        return influential_paths[:20]  # 返回 top 20


class CentralityAnalyzer:
    """中心性分析器

    計算各種中心性指標，識別關鍵概念
    """

    def __init__(self, network: ConceptNetwork):
        self.network = network

    def calculate_all_centralities(self) -> List[CentralityScores]:
        """計算所有中心性指標"""
        results = []

        for node_id in self.network.node_dict.keys():
            scores = CentralityScores(
                node_id=node_id,
                degree_centrality=self._degree_centrality(node_id),
                betweenness_centrality=self._betweenness_centrality(node_id),
                closeness_centrality=self._closeness_centrality(node_id),
                pagerank=0.0  # 稍後計算
            )
            results.append(scores)

        # 計算 PageRank
        pagerank_scores = self._calculate_pagerank()
        for scores in results:
            scores.pagerank = pagerank_scores.get(scores.node_id, 0.0)

        return results

    def _degree_centrality(self, node_id: str) -> float:
        """度中心性：歸一化度數"""
        degree = self.network.node_dict[node_id]['degree']
        n = self.network.node_count()
        return degree / (n - 1) if n > 1 else 0.0

    def _betweenness_centrality(self, node_id: str) -> float:
        """中介中心性：經過該節點的最短路徑比例"""
        # 簡化版：只計算部分節點對
        total_paths = 0
        paths_through_node = 0

        # 隨機採樣節點對（避免計算所有對）
        nodes = list(self.network.node_dict.keys())
        sample_size = min(50, len(nodes))

        import random
        sampled_pairs = []
        for _ in range(sample_size):
            s = random.choice(nodes)
            t = random.choice(nodes)
            if s != t and s != node_id and t != node_id:
                sampled_pairs.append((s, t))

        for s, t in sampled_pairs:
            # 找最短路徑
            path = self._bfs_shortest_path(s, t)
            if path:
                total_paths += 1
                if node_id in path:
                    paths_through_node += 1

        return paths_through_node / total_paths if total_paths > 0 else 0.0

    def _closeness_centrality(self, node_id: str) -> float:
        """接近中心性：到其他節點的平均距離倒數"""
        # BFS 計算距離
        distances = self._bfs_distances(node_id)

        if not distances:
            return 0.0

        avg_distance = sum(distances.values()) / len(distances)
        return 1.0 / avg_distance if avg_distance > 0 else 0.0

    def _calculate_pagerank(
        self,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-6
    ) -> Dict[str, float]:
        """計算 PageRank"""
        nodes = list(self.network.node_dict.keys())
        n = len(nodes)

        # 初始化
        ranks = {node: 1.0 / n for node in nodes}

        # 迭代
        for _ in range(max_iterations):
            new_ranks = {}
            max_diff = 0.0

            for node in nodes:
                rank_sum = 0.0

                # 計算來自鄰居的貢獻
                for neighbor in self.network.get_neighbors(node):
                    neighbor_degree = self.network.node_dict[neighbor]['degree']
                    if neighbor_degree > 0:
                        rank_sum += ranks[neighbor] / neighbor_degree

                new_rank = (1 - damping) / n + damping * rank_sum
                new_ranks[node] = new_rank

                # 檢查收斂
                diff = abs(new_rank - ranks[node])
                max_diff = max(max_diff, diff)

            ranks = new_ranks

            if max_diff < tolerance:
                break

        return ranks

    def _bfs_shortest_path(self, start: str, end: str) -> Optional[List[str]]:
        """BFS 最短路徑"""
        if start == end:
            return [start]

        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            node, path = queue.popleft()

            for neighbor in self.network.get_neighbors(node):
                if neighbor == end:
                    return path + [neighbor]

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    def _bfs_distances(self, start: str) -> Dict[str, int]:
        """BFS 計算距離"""
        distances = {}
        queue = deque([(start, 0)])
        visited = {start}

        while queue:
            node, dist = queue.popleft()

            for neighbor in self.network.get_neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    distances[neighbor] = dist + 1
                    queue.append((neighbor, dist + 1))

        return distances

    def get_top_nodes(
        self,
        metric: str = 'pagerank',
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """獲取 top-k 節點

        參數:
            metric: 'degree', 'betweenness', 'closeness', 'pagerank'
            top_k: 返回數量
        """
        centralities = self.calculate_all_centralities()

        if metric == 'degree':
            key_func = lambda c: c.degree_centrality
        elif metric == 'betweenness':
            key_func = lambda c: c.betweenness_centrality
        elif metric == 'closeness':
            key_func = lambda c: c.closeness_centrality
        elif metric == 'pagerank':
            key_func = lambda c: c.pagerank
        else:
            raise ValueError(f"Unknown metric: {metric}")

        sorted_centralities = sorted(centralities, key=key_func, reverse=True)

        return [(c.node_id, key_func(c)) for c in sorted_centralities[:top_k]]


class NetworkVisualizer:
    """網絡視覺化引擎

    生成互動式網絡圖（D3.js / Graphviz）
    """

    def __init__(self, network: ConceptNetwork):
        self.network = network

    def generate_d3_html(
        self,
        output_path: str,
        communities: Optional[List[Community]] = None,
        centralities: Optional[List[CentralityScores]] = None,
        title: str = "Zettelkasten Concept Network"
    ):
        """生成 D3.js 互動式網絡圖

        參數:
            output_path: 輸出 HTML 文件路徑
            communities: 社群列表（用於著色）
            centralities: 中心性分數（用於節點大小）
            title: 圖表標題
        """
        # 準備數據
        nodes_data = self._prepare_nodes_data(communities, centralities)
        edges_data = self._prepare_edges_data()

        # 生成 HTML
        html_content = self._generate_d3_html_template(
            nodes_data, edges_data, title
        )

        # 寫入文件
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html_content, encoding='utf-8')

        print(f"✅ D3.js 互動式網絡圖已生成: {output_path}")

    def _prepare_nodes_data(
        self,
        communities: Optional[List[Community]],
        centralities: Optional[List[CentralityScores]]
    ) -> List[Dict]:
        """準備節點數據"""
        # 建立社群映射
        node_to_community = {}
        if communities:
            for comm in communities:
                for node in comm.nodes:
                    node_to_community[node] = comm.community_id

        # 建立中心性映射
        node_to_centrality = {}
        if centralities:
            for c in centralities:
                node_to_centrality[c.node_id] = c.pagerank

        # 構建節點數據
        nodes_data = []
        for node in self.network.nodes:
            node_id = node['card_id']
            nodes_data.append({
                'id': node_id,
                'label': node['title'][:40],  # 截斷標題
                'degree': node['degree'],
                'community': node_to_community.get(node_id, 0),
                'centrality': node_to_centrality.get(node_id, 0.0)
            })

        return nodes_data

    def _prepare_edges_data(self) -> List[Dict]:
        """準備邊數據"""
        edges_data = []
        for edge in self.network.edges:
            edges_data.append({
                'source': edge['source'],
                'target': edge['target'],
                'type': edge['relation_type'],
                'confidence': edge['confidence']
            })

        return edges_data

    def _generate_d3_html_template(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        title: str
    ) -> str:
        """生成 D3.js HTML 模板"""
        nodes_json = json.dumps(nodes, ensure_ascii=False, indent=2)
        edges_json = json.dumps(edges, ensure_ascii=False, indent=2)

        html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f5f5;
        }}

        #title {{
            text-align: center;
            color: #333;
            margin-bottom: 20px;
        }}

        #stats {{
            text-align: center;
            color: #666;
            margin-bottom: 10px;
        }}

        #network {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .node {{
            stroke: #fff;
            stroke-width: 2px;
            cursor: pointer;
        }}

        .node:hover {{
            stroke: #000;
            stroke-width: 3px;
        }}

        .link {{
            stroke: #999;
            stroke-opacity: 0.6;
        }}

        .link.leads_to {{ stroke: #3498db; }}
        .link.based_on {{ stroke: #9b59b6; }}
        .link.related_to {{ stroke: #95a5a6; }}
        .link.contrasts_with {{ stroke: #e74c3c; }}
        .link.superclass_of {{ stroke: #2ecc71; }}
        .link.subclass_of {{ stroke: #f39c12; }}

        .label {{
            font-size: 10px;
            fill: #333;
            pointer-events: none;
        }}

        #tooltip {{
            position: absolute;
            padding: 10px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            border-radius: 5px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
            max-width: 300px;
        }}

        #legend {{
            position: absolute;
            top: 80px;
            right: 20px;
            background: white;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .legend-item {{
            margin: 5px 0;
            display: flex;
            align-items: center;
        }}

        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 3px;
            margin-right: 8px;
        }}
    </style>
</head>
<body>
    <h1 id="title">{title}</h1>
    <div id="stats">節點數: {len(nodes)} | 邊數: {len(edges)}</div>
    <div id="network"></div>
    <div id="tooltip"></div>
    <div id="legend">
        <h3 style="margin-top: 0;">關係類型</h3>
        <div class="legend-item">
            <div class="legend-color" style="background: #3498db;"></div>
            <span>Leads To (導向)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #9b59b6;"></div>
            <span>Based On (基於)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #95a5a6;"></div>
            <span>Related To (相關)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #e74c3c;"></div>
            <span>Contrasts With (對比)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #2ecc71;"></div>
            <span>Superclass Of (上位)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #f39c12;"></div>
            <span>Subclass Of (下位)</span>
        </div>
    </div>

    <script>
        // 數據
        const nodes = {nodes_json};
        const edges = {edges_json};

        // 設定
        const width = window.innerWidth - 40;
        const height = window.innerHeight - 200;

        // 創建 SVG
        const svg = d3.select("#network")
            .append("svg")
            .attr("width", width)
            .attr("height", height);

        // 創建力導向圖
        const simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(edges).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(30));

        // 繪製邊
        const link = svg.append("g")
            .selectAll("line")
            .data(edges)
            .enter()
            .append("line")
            .attr("class", d => `link ${{d.type}}`)
            .attr("stroke-width", d => Math.sqrt(d.confidence * 5));

        // 繪製節點
        const node = svg.append("g")
            .selectAll("circle")
            .data(nodes)
            .enter()
            .append("circle")
            .attr("class", "node")
            .attr("r", d => 5 + Math.sqrt(d.degree) * 3)
            .attr("fill", d => d3.schemeCategory10[d.community % 10])
            .call(drag(simulation));

        // 節點標籤
        const label = svg.append("g")
            .selectAll("text")
            .data(nodes)
            .enter()
            .append("text")
            .attr("class", "label")
            .attr("dx", 12)
            .attr("dy", 4)
            .text(d => d.label);

        // Tooltip
        const tooltip = d3.select("#tooltip");

        node.on("mouseover", function(event, d) {{
            tooltip.style("opacity", 1)
                .html(`
                    <strong>${{d.label}}</strong><br>
                    ID: ${{d.id}}<br>
                    度: ${{d.degree}}<br>
                    社群: ${{d.community}}<br>
                    PageRank: ${{d.centrality.toFixed(4)}}
                `)
                .style("left", (event.pageX + 10) + "px")
                .style("top", (event.pageY - 10) + "px");
        }})
        .on("mouseout", function() {{
            tooltip.style("opacity", 0);
        }});

        // 更新位置
        simulation.on("tick", () => {{
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);

            label
                .attr("x", d => d.x)
                .attr("y", d => d.y);
        }});

        // 拖曳功能
        function drag(simulation) {{
            function dragstarted(event) {{
                if (!event.active) simulation.alphaTarget(0.3).restart();
                event.subject.fx = event.subject.x;
                event.subject.fy = event.subject.y;
            }}

            function dragged(event) {{
                event.subject.fx = event.x;
                event.subject.fy = event.y;
            }}

            function dragended(event) {{
                if (!event.active) simulation.alphaTarget(0);
                event.subject.fx = null;
                event.subject.fy = null;
            }}

            return d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended);
        }}
    </script>
</body>
</html>'''

        return html

    def generate_graphviz_dot(
        self,
        output_path: str,
        communities: Optional[List[Community]] = None,
        max_nodes: int = 100
    ):
        """生成 Graphviz DOT 格式

        參數:
            output_path: 輸出 .dot 文件路徑
            communities: 社群列表（用於著色）
            max_nodes: 最大節點數（避免圖過大）
        """
        # 限制節點數
        top_nodes = sorted(
            self.network.nodes,
            key=lambda n: n['degree'],
            reverse=True
        )[:max_nodes]

        top_node_ids = {n['card_id'] for n in top_nodes}

        # 建立社群映射
        node_to_community = {}
        if communities:
            for comm in communities:
                for node in comm.nodes:
                    node_to_community[node] = comm.community_id

        # 生成 DOT
        lines = ['digraph ConceptNetwork {']
        lines.append('    rankdir=LR;')
        lines.append('    node [shape=box, style=rounded];')
        lines.append('')

        # 節點
        for node in top_nodes:
            node_id = node['card_id']
            label = node['title'][:30]
            community = node_to_community.get(node_id, 0)
            color = ['lightblue', 'lightgreen', 'lightyellow', 'lightpink', 'lightgray'][community % 5]

            lines.append(f'    "{node_id}" [label="{label}", fillcolor="{color}", style="filled,rounded"];')

        lines.append('')

        # 邊
        for edge in self.network.edges:
            if edge['source'] in top_node_ids and edge['target'] in top_node_ids:
                rel_type = edge['relation_type']
                confidence = edge['confidence']

                # 邊樣式
                style = {
                    'leads_to': 'solid',
                    'based_on': 'dashed',
                    'related_to': 'dotted',
                    'contrasts_with': 'bold',
                    'superclass_of': 'solid',
                    'subclass_of': 'solid'
                }.get(rel_type, 'solid')

                lines.append(
                    f'    "{edge["source"]}" -> "{edge["target"]}" '
                    f'[label="{rel_type}", style="{style}", penwidth={confidence*3:.1f}];'
                )

        lines.append('}')

        # 寫入文件
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text('\n'.join(lines), encoding='utf-8')

        print(f"✅ Graphviz DOT 文件已生成: {output_path}")
        print(f"   提示: 使用 `dot -Tpng {output_path} -o output.png` 生成圖片")


class ConceptMapper:
    """概念映射器主類

    整合所有分析和視覺化功能
    """

    def __init__(self, kb_path: str = "knowledge_base"):
        self.kb_path = kb_path
        self.relation_finder = RelationFinder(kb_path=kb_path)
        self.network = None

    def build_network(
        self,
        min_similarity: float = 0.4,
        min_confidence: float = 0.3
    ) -> ConceptNetwork:
        """建構概念網絡"""
        print("📊 建構概念網絡...")
        network_data = self.relation_finder.build_concept_network(
            min_similarity=min_similarity,
            min_confidence=min_confidence
        )
        self.network = ConceptNetwork(network_data)
        return self.network

    def analyze_all(
        self,
        output_dir: str = "output/concept_analysis",
        visualize: bool = True,
        obsidian_mode: bool = False,
        obsidian_options: Optional[Dict] = None
    ) -> Dict:
        """執行所有分析並生成報告

        參數:
            output_dir: 輸出目錄
            visualize: 是否生成視覺化
            obsidian_mode: 是否生成 Obsidian 友好格式
            obsidian_options: Obsidian 導出選項

        返回:
            Dict: 完整分析結果
        """
        if self.network is None:
            self.build_network()

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        print("\n" + "="*70)
        print("🔍 Phase 2.2: 概念網絡全面分析")
        print("="*70)

        # 1. 社群檢測
        print("\n[1] 社群檢測分析...")
        community_detector = CommunityDetector(self.network)
        communities = community_detector.detect_communities(method='louvain')
        print(f"   檢測到 {len(communities)} 個社群")

        # 2. 路徑分析
        print("\n[2] 路徑分析...")
        path_analyzer = PathAnalyzer(self.network)
        influential_paths = path_analyzer.find_influential_paths()
        print(f"   識別到 {len(influential_paths)} 條有影響力的路徑")

        # 3. 中心性分析
        print("\n[3] 中心性分析...")
        centrality_analyzer = CentralityAnalyzer(self.network)
        centralities = centrality_analyzer.calculate_all_centralities()
        top_pagerank = centrality_analyzer.get_top_nodes('pagerank', 10)
        print(f"   計算了 {len(centralities)} 個節點的中心性")

        # 4. 生成視覺化
        if visualize:
            print("\n[4] 生成視覺化...")
            visualizer = NetworkVisualizer(self.network)

            # D3.js 互動式網絡圖
            html_path = output_path / "concept_network.html"
            visualizer.generate_d3_html(
                str(html_path),
                communities=communities,
                centralities=centralities
            )

            # Graphviz DOT
            dot_path = output_path / "concept_network.dot"
            visualizer.generate_graphviz_dot(
                str(dot_path),
                communities=communities
            )

        # 5. 生成報告
        print("\n[5] 生成分析報告...")
        report = self._generate_report(
            communities, influential_paths, centralities, top_pagerank
        )

        report_path = output_path / "analysis_report.md"
        report_path.write_text(report, encoding='utf-8')
        print(f"   分析報告: {report_path}")

        # 6. 導出 JSON
        json_path = output_path / "analysis_data.json"
        json_data = {
            'network_statistics': self.network.statistics,
            'relations': self.network.relations,  # ✅ 修復：添加關係數據（已經是字典列表）
            'communities': [asdict(c) for c in communities],
            'influential_paths': [asdict(p) for p in influential_paths],
            'top_pagerank_nodes': top_pagerank
        }
        json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"   JSON 數據: {json_path}")

        # 7. Obsidian 友好格式導出（可選）
        if obsidian_mode:
            from claude_lit.analyzers.obsidian_exporter import ObsidianExporter

            print("\n[6] 生成 Obsidian 友好格式...")
            exporter = ObsidianExporter(kb_path=self.kb_path)

            obsidian_dir = output_path / "obsidian"
            exporter.export_all(
                analysis_results={
                    'relations': self.network.relations,  # 已經是字典列表
                    'centralities': centralities,
                    'communities': communities,
                    'paths': influential_paths,
                    'network_statistics': self.network.statistics
                },
                output_dir=str(obsidian_dir),
                options=obsidian_options
            )

        print("\n" + "="*70)
        print("✅ Phase 2.2 分析完成！")
        print(f"   輸出目錄: {output_path}")
        if obsidian_mode:
            print(f"   Obsidian 輸出: {output_path / 'obsidian'}")
        print("="*70 + "\n")

        return {
            'network': self.network,
            'communities': communities,
            'paths': influential_paths,
            'centralities': centralities,
            'output_dir': str(output_path)
        }

    def _generate_report(
        self,
        communities: List[Community],
        paths: List[ConceptPath],
        centralities: List[CentralityScores],
        top_pagerank: List[Tuple[str, float]]
    ) -> str:
        """生成 Markdown 分析報告"""
        lines = ["# Zettelkasten 概念網絡分析報告\n"]
        lines.append(f"**生成時間**: {self._get_timestamp()}\n")
        lines.append(f"**知識庫路徑**: {self.kb_path}\n")
        lines.append("\n---\n")

        # 網絡統計
        lines.append("## 1. 網絡統計概覽\n")
        stats = self.network.statistics
        lines.append(f"- **節點數**: {stats.get('node_count', 0)}")
        lines.append(f"- **邊數**: {stats.get('edge_count', 0)}")
        lines.append(f"- **平均度**: {stats.get('avg_degree', 0):.2f}")
        lines.append(f"- **最大度**: {stats.get('max_degree', 0)}")
        lines.append(f"- **網絡密度**: {stats.get('density', 0):.4f}\n")

        # 社群分析
        lines.append("## 2. 社群檢測結果\n")
        lines.append(f"檢測到 **{len(communities)}** 個概念社群：\n")

        for comm in communities[:10]:  # 只顯示前 10 個
            lines.append(f"### 社群 {comm.community_id}\n")
            lines.append(f"- **大小**: {comm.size} 個節點")
            lines.append(f"- **密度**: {comm.density:.3f}")
            lines.append(f"- **中心節點**: {comm.hub_node}")
            lines.append(f"- **核心概念**:")
            for concept in comm.top_concepts[:3]:
                lines.append(f"  - {concept}")
            lines.append("")

        # 路徑分析
        lines.append("## 3. 有影響力的概念路徑\n")
        lines.append(f"識別到 **{len(paths)}** 條連接核心概念的路徑。Top 5:\n")

        for i, path in enumerate(paths[:5], 1):
            path_str = " → ".join([self.network.node_dict[nid]['title'][:20] for nid in path.path])
            lines.append(f"{i}. **長度**: {path.length}, **信度**: {path.confidence:.2f}")
            lines.append(f"   ```")
            lines.append(f"   {path_str}")
            lines.append(f"   ```\n")

        # 中心性分析
        lines.append("## 4. 關鍵概念識別（PageRank）\n")
        lines.append("Top 10 最具影響力的概念：\n")
        lines.append("| 排名 | 卡片 ID | PageRank | 標題 |")
        lines.append("|------|---------|----------|------|")

        for i, (node_id, score) in enumerate(top_pagerank, 1):
            title = self.network.node_dict[node_id]['title'][:40]
            lines.append(f"| {i} | {node_id} | {score:.4f} | {title} |")

        lines.append("\n---\n")
        lines.append("**分析方法**:")
        lines.append("- 社群檢測: Louvain 算法")
        lines.append("- 路徑分析: BFS 最短路徑")
        lines.append("- 中心性分析: PageRank + Betweenness + Closeness + Degree")

        return "\n".join(lines)

    def _get_timestamp(self) -> str:
        """獲取時間戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 測試代碼
if __name__ == "__main__":
    mapper = ConceptMapper()

    # 建構網絡
    network = mapper.build_network(min_similarity=0.4, min_confidence=0.3)

    # 執行所有分析
    results = mapper.analyze_all(
        output_dir="output/concept_analysis",
        visualize=True,
        obsidian_mode=True  # 啟用 Obsidian 模式測試
    )

    print("✅ 分析完成！")
    print(f"   社群數: {len(results['communities'])}")
    print(f"   路徑數: {len(results['paths'])}")
    print(f"   輸出目錄: {results['output_dir']}")
