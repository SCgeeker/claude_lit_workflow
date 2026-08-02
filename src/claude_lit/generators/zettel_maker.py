"""
Zettelkasten原子筆記生成器
支援語義化ID、概念連結網絡、Markdown輸出
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict

try:
    from jinja2 import Template
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ZettelMaker:
    """
    Zettelkasten原子筆記生成器
    基於文獻內容生成原子化知識卡片
    """

    def __init__(self,
                 card_template_path: Optional[str] = None,
                 index_template_path: Optional[str] = None,
                 styles_config: Optional[str] = None):
        """
        初始化Zettelkasten生成器

        Args:
            card_template_path: 卡片模板路徑
            index_template_path: 索引模板路徑
            styles_config: 風格配置路徑
        """
        if not JINJA2_AVAILABLE:
            raise ImportError("Jinja2 not installed. Run: pip install jinja2")

        if not YAML_AVAILABLE:
            raise ImportError("PyYAML not installed. Run: pip install pyyaml")

        # 載入模板與風格配置（解析順序：明確參數 > cwd 使用者檔 > 套件內建）
        from claude_lit.resource_loader import resolve_resource

        card_template_path = resolve_resource(
            "templates/markdown/zettelkasten_card.jinja2", explicit=card_template_path
        )
        with open(card_template_path, 'r', encoding='utf-8') as f:
            self.card_template = Template(f.read())

        index_template_path = resolve_resource(
            "templates/markdown/zettelkasten_index.jinja2", explicit=index_template_path
        )
        with open(index_template_path, 'r', encoding='utf-8') as f:
            self.index_template = Template(f.read())

        styles_config = resolve_resource(
            "templates/styles/academic_styles.yaml", explicit=styles_config
        )

        with open(styles_config, 'r', encoding='utf-8') as f:
            self.styles_config = yaml.safe_load(f)

        self.zettel_config = self.styles_config['styles']['zettelkasten']

    def generate_card_id(self, cite_key: str, sequence: int) -> str:
        """
        生成卡片ID（基於 cite_key）

        Args:
            cite_key: 論文的 bibtex cite_key
            sequence: 序號

        Returns:
            格式化ID（如 Her2007-001, Abbas-2022-001）
        """
        return f"{cite_key}-{sequence:03d}"

    def parse_llm_output(
        self, llm_output: str, cite_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        解析LLM生成的Zettelkasten卡片內容

        期望格式：
        ===CARD: {card_id}===
        標題: {title}
        類型: {concept|method|finding|question}
        核心: {one_sentence}
        標籤: {tag1}, {tag2}

        說明:
        {detailed_explanation}

        連結:
        基於 -> {card_id1}, {card_id2}
        導向 -> {card_id3}
        相關 <-> {card_id4}
        對比 <-> {card_id5}

        個人筆記:
        {notes}

        待解問題:
        {questions}
        ===

        Args:
            llm_output: LLM生成的文本
            cite_key: 論文 cite_key。給定時卡片 ID 由 cite_key + 序號決定，
                不採信 LLM 自報的 ID（模型會漂移成別篇論文的 citekey）。

        Returns:
            卡片數據列表
        """
        # 使用正則分割卡片
        card_pattern = r'===CARD:\s*([^=]+)==='
        parts = re.split(card_pattern, llm_output)

        cards = []

        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                card_id = parts[i].strip()
                # 去掉卡片結尾的 === 分隔符，避免殘留在最後一個章節裡
                card_content = re.sub(r'\n\s*===\s*$', '', parts[i + 1].strip()).strip()

                card_data = self._parse_single_card(card_id, card_content)
                if card_data:
                    cards.append(card_data)

        if cite_key:
            self.canonicalize_card_ids(cards, cite_key)

        return cards

    _LINK_FIELDS = (
        'foundation_links', 'derived_links', 'related_links', 'contrast_links'
    )

    def canonicalize_card_ids(self, cards: List[Dict[str, Any]], cite_key: str) -> List[Dict[str, Any]]:
        """把 LLM 自報的卡片 ID 重編為 {cite_key}-{序號}，並同步改寫卡內連結。

        LLM 的 ID 會漂移（補零消失、退化成別篇論文的 citekey），髒 ID 進了知識庫
        就可能與真實 citekey 撞號，因此改由程式決定；對不上的連結視為幻覺，丟棄。

        就地修改 cards 並回傳同一清單（供 grounding gate 過濾後重編存活卡片）。
        """
        id_map = {}
        for index, card in enumerate(cards, start=1):
            new_id = self.generate_card_id(cite_key, index)
            id_map[card['id']] = new_id
            card['id'] = new_id

        for card in cards:
            for field in self._LINK_FIELDS:
                card[field] = [
                    id_map[link] for link in card[field] if link in id_map
                ]
            for field in self._FREE_TEXT_FIELDS:
                if card.get(field):
                    card[field] = self._rewrite_inline_links(card[field], id_map)

        return cards

    # 自由文字欄位也可能含 [[...]]（模板要求 AI 註記至少帶一個連結）
    _FREE_TEXT_FIELDS = (
        'detailed_explanation', 'personal_notes', 'open_questions', 'source_context'
    )

    def _rewrite_inline_links(self, text: str, id_map: Dict[str, str]) -> str:
        """改寫自由文字中的 [[卡片ID]]；對不上的退成純文字，避免筆記 App 死連結。

        含 `|`（顯示文字）或 .pdf 的連結屬來源文獻連結，不動。
        """
        if not text:
            return text

        def replace(match):
            target = match.group(1)
            if '|' in target or target.endswith('.pdf'):
                return match.group(0)
            if target in id_map:
                return f"[[{id_map[target]}]]"
            return target

        return re.sub(r'\[\[([^\]]+)\]\]', replace, text)

    def _parse_single_card(self, card_id: str, content: str) -> Optional[Dict[str, Any]]:
        """解析單張卡片內容"""
        card = {
            'id': card_id,
            'title': '',
            'card_type': 'concept',
            'core_summary': '',
            'tags': [],
            'detailed_explanation': '',
            'foundation_links': [],
            'derived_links': [],
            'related_links': [],
            'contrast_links': [],
            'personal_notes': '',
            'open_questions': ''
        }

        # 解析欄位
        lines = content.split('\n')
        current_section = None
        section_content = []

        for line in lines:
            line_stripped = line.strip()

            # 識別欄位
            if line_stripped.startswith('標題:') or line_stripped.startswith('Title:'):
                card['title'] = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith('類型:') or line_stripped.startswith('Type:'):
                card['card_type'] = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith('核心:') or line_stripped.startswith('Core:'):
                card['core_summary'] = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith('標籤:') or line_stripped.startswith('Tags:'):
                tags_str = line_stripped.split(':', 1)[1].strip()
                card['tags'] = [t.strip() for t in tags_str.split(',')]

            # 識別章節（在切換前先保存舊章節內容）
            elif (section := self._match_section_header(line_stripped)):
                self._save_section_content(current_section, section_content, card)
                current_section = section
                section_content = []

            # 收集章節內容
            elif current_section:
                if current_section == 'links':
                    self._parse_link_line(line_stripped, card)
                else:
                    section_content.append(line)

        # 保存最後一個章節
        self._save_section_content(current_section, section_content, card)

        return card if card['title'] else None

    # 章節關鍵詞（依序比對）。小模型常寫出錯字變體 —— 實測見過
    # 「連結語系」「來源脈索」「個人筆目」—— 嚴格字串比對認不得就會讓整段
    # 落進上一節，連結因此永遠進不了 links 欄位，故改以關鍵詞辨識。
    _SECTION_KEYWORDS = (
        ('links', ('連結', 'links')),
        ('source_context', ('來源', 'source context')),
        ('notes', ('個人', 'personal notes')),
        ('questions', ('待解', 'open questions')),
        ('explanation', ('說明', 'explanation')),
    )
    _HEADER_MAX_LEN = 20

    def _match_section_header(self, line: str) -> Optional[str]:
        """判斷此行是否為章節標頭，回傳章節名稱（非標頭則 None）。

        條件：去掉 markdown 記號與結尾冒號後夠短，且含章節關鍵詞。
        """
        core = line.strip().lstrip('#*-　 ').strip()
        if not core.endswith((':', '：')):
            return None
        core = core.rstrip(':：').strip().rstrip('*').strip()
        if not core or len(core) > self._HEADER_MAX_LEN:
            return None

        lowered = core.lower()
        for section, keywords in self._SECTION_KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                return section
        return None

    def _save_section_content(self, section: Optional[str], content: List[str], card: Dict[str, Any]):
        """保存章節內容到卡片"""
        if not section or not content:
            return

        content_text = '\n'.join(content).strip()
        if not content_text:
            return

        if section == 'explanation':
            card['detailed_explanation'] = content_text
        elif section == 'source_context':
            # 解析來源脈絡的位置和情境
            for line in content:
                line_stripped = line.strip()
                if line_stripped.startswith('- **位置'):
                    # 提取位置信息（例如：- **位置**: Methods）
                    if ':' in line_stripped:
                        card['section'] = line_stripped.split(':', 1)[1].strip()
                elif line_stripped.startswith('- **情境'):
                    # 提取情境信息
                    if ':' in line_stripped:
                        card['context'] = line_stripped.split(':', 1)[1].strip()
            # 保存完整的來源脈絡文本
            card['source_context'] = content_text
        elif section == 'notes':
            card['personal_notes'] = content_text
        elif section == 'questions':
            card['open_questions'] = content_text

    def _parse_link_line(self, line: str, card: Dict[str, Any]):
        """解析連結行"""
        if '基於' in line or 'foundation' in line.lower():
            links = self._extract_links(line)
            card['foundation_links'].extend(links)
        elif '導向' in line or 'derived' in line.lower():
            links = self._extract_links(line)
            card['derived_links'].extend(links)
        elif '相關' in line or 'related' in line.lower():
            links = self._extract_links(line)
            card['related_links'].extend(links)
        elif '對比' in line or 'contrast' in line.lower():
            links = self._extract_links(line)
            card['contrast_links'].extend(links)

    def _extract_links(self, line: str) -> List[str]:
        """從行中提取連結ID"""
        links = []

        # 方法 1: 先嘗試從 [[...]] 中提取（Obsidian Wiki Links 格式）
        wiki_link_pattern = r'\[\[([^\]]+)\]\]'
        wiki_matches = re.findall(wiki_link_pattern, line)
        if wiki_matches:
            for match in wiki_matches:
                # 移除可能的顯示文本（格式：[[link|display]]）
                link_id = match.split('|')[0].strip()
                # 過濾空白連結、PDF連結、和無效格式
                if link_id and not link_id.endswith('.pdf') and not link_id.startswith('-') and len(link_id) > 2:
                    links.append(link_id)
            return links

        # 方法 2: 傳統格式（如果沒有 Wiki Links）
        # 移除箭頭和符號（但保留破折號）
        line = re.sub(r'[→←↔⚡⬆⬇><]', '', line)
        # 移除欄位名稱
        line = re.sub(r'(基於|導向|相關|對比|foundation|derived|related|contrast)', '', line, flags=re.IGNORECASE)

        # 分割並清理
        parts = line.split(',')
        for part in parts:
            part = part.strip()
            # 過濾無效格式：空字串、只有標點、只有格式符號
            if not part or part.endswith(':') or part.endswith('.pdf'):
                continue
            # 過濾 Markdown 格式符號（例如：- ****, ***, --, 等）
            if re.match(r'^[\-\*\s]+$', part):
                continue
            # 過濾開頭為 '-' 或長度不足的連結
            if part.startswith('-') or len(part) < 3:
                continue

            # 檢測舊格式：XXX20251028001 → XXX-20251028-001
            match = re.match(r'^([A-Za-z]+)(\d{8})(\d{3})$', part)
            if match:
                domain, date, seq = match.groups()
                part = f"{domain}-{date}-{seq}"
            links.append(part)

        return links

    def create_card_file(self,
                        card_data: Dict[str, Any],
                        output_dir: Path,
                        paper_info: Dict[str, str]) -> str:
        """
        創建單張卡片Markdown文件

        Args:
            card_data: 卡片數據
            output_dir: 輸出目錄
            paper_info: 論文信息（title, authors, year, citation等）

        Returns:
            輸出文件路徑
        """
        # 合併論文信息（優先使用卡片級別的值）
        render_data = {
            **card_data,
            'paper_title': paper_info.get('title', ''),
            'year': paper_info.get('year', ''),
            'paper_id': paper_info.get('paper_id', ''),
            'citation': paper_info.get('citation', ''),
            'cite_key': paper_info.get('cite_key', ''),
            'created_date': datetime.now().strftime("%Y-%m-%d"),
            # 優先使用卡片級別的來源脈絡信息
            'section': card_data.get('section') or paper_info.get('section', ''),
            'page_number': card_data.get('page_number') or paper_info.get('page', ''),
            'context': card_data.get('context') or paper_info.get('context', ''),
            'confidence': paper_info.get('confidence', '')
        }

        # 渲染模板
        markdown_content = self.card_template.render(**render_data)

        # 保存文件
        output_path = output_dir / f"{card_data['id']}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        return str(output_path)

    def create_index_file(self,
                         cards: List[Dict[str, Any]],
                         output_path: Path,
                         paper_info: Dict[str, str]) -> str:
        """
        創建卡片索引文件

        Args:
            cards: 所有卡片數據
            output_path: 輸出路徑
            paper_info: 論文信息

        Returns:
            輸出文件路徑
        """
        # 按標籤分組
        cards_by_tag = defaultdict(list)
        for card in cards:
            for tag in card['tags']:
                cards_by_tag[tag].append(card)

        # 建議閱讀順序（基於連結關係的拓撲排序簡化版）
        reading_order = self._suggest_reading_order(cards)

        # 渲染模板
        markdown_content = self.index_template.render(
            paper_title=paper_info.get('title', ''),
            authors=paper_info.get('authors', ''),
            year=paper_info.get('year', ''),
            generated_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            card_count=len(cards),
            cards=cards,
            cards_by_tag=dict(cards_by_tag),
            reading_order=reading_order,
            cite_key=paper_info.get('cite_key', '')
        )

        # 保存文件
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        return str(output_path)

    def _suggest_reading_order(self, cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """建議閱讀順序（簡化的拓撲排序）"""
        # 計算每張卡片的依賴數（被多少卡片依賴）
        dependency_count = {card['id']: 0 for card in cards}
        card_map = {card['id']: card for card in cards}

        for card in cards:
            for linked_id in card.get('foundation_links', []):
                if linked_id in dependency_count:
                    dependency_count[linked_id] += 1

        # 按依賴數排序（依賴少的先讀）
        sorted_cards = sorted(cards, key=lambda c: dependency_count[c['id']])

        return sorted_cards

    def generate_zettelkasten(self,
                             llm_output: Optional[str] = None,
                             output_dir: Path = None,
                             paper_info: Dict[str, str] = None,
                             cards: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        完整生成Zettelkasten卡片集

        Args:
            llm_output: LLM生成的內容（未傳 cards 時用於解析）
            output_dir: 輸出目錄
            paper_info: 論文信息
            cards: 已解析/過濾/編號的卡片清單。傳入時**跳過內部重新解析**，直接寫檔——
                供 grounding gate 在 api 層過濾後，把存活卡片交給寫檔（見 api/zettel）。

        Returns:
            生成結果
        """
        # 1. 取得卡片：優先用傳入的已處理清單（gate 過濾後），否則解析 llm_output
        #    （cite_key 存在時由程式決定卡片 ID，見 canonicalize_card_ids）
        if cards is None:
            cards = self.parse_llm_output(llm_output or "", cite_key=paper_info.get('cite_key'))

        if not cards:
            # 保存原始輸出用於調試（僅在有 llm_output 時）
            debug_file = output_dir.parent / f"debug_llm_output_{output_dir.name}.txt"
            if llm_output:
                debug_file.write_text(llm_output, encoding='utf-8')
            raise ValueError(f"無法解析任何卡片，請檢查LLM輸出格式。原始輸出已保存至: {debug_file}")

        # 2. 創建卡片目錄
        cards_dir = output_dir / "zettel_cards"
        cards_dir.mkdir(parents=True, exist_ok=True)

        # 3. 生成獨立卡片文件
        card_files = []
        for card in cards:
            card_path = self.create_card_file(card, cards_dir, paper_info)
            card_files.append(card_path)

        # 4. 生成索引文件
        index_path = output_dir / "zettel_index.md"
        index_file = self.create_index_file(cards, index_path, paper_info)

        return {
            'success': True,
            'card_count': len(cards),
            'card_files': card_files,
            'index_file': index_file,
            'output_dir': str(output_dir)
        }


if __name__ == "__main__":
    # 測試代碼
    print("Zettelkasten Maker 模組已載入")
    print("用法: from claude_lit.generators import ZettelMaker")
