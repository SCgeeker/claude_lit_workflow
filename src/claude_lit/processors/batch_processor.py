#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批次處理器 (Batch Processor)

功能:
1. 穩定地批次處理大量PDF文件
2. 解決 Windows 路徑編碼問題
3. 支援平行處理
4. 進度追蹤和錯誤處理
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

# 注意：庫模組不得在 import 時重新包裝 sys.stdout / sys.stderr
# （會關閉 pytest capture 與 MCP stdio 的底層串流）；編碼防護由 CLI 入口負責。

# 添加專案根目錄到路徑



@dataclass
class ProcessResult:
    """單個文件處理結果"""
    file_path: str
    success: bool
    paper_id: Optional[int] = None
    zettel_dir: Optional[str] = None
    error: Optional[str] = None
    processing_time: float = 0.0
    zettel_imported_to_db: int = 0  # ✅ 新增：導入到數據庫的卡片數
    zettel_failed_import: int = 0   # ✅ 新增：導入失敗的卡片數

    def to_dict(self) -> dict:
        """轉為字典"""
        return asdict(self)


@dataclass
class BatchResult:
    """批次處理結果"""
    total: int
    success: int
    failed: int
    errors: List[Dict[str, str]] = field(default_factory=list)
    processing_time: str = ""
    papers_added_to_kb: int = 0
    zettel_generated: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)

    # 詳細結果列表
    results: List[ProcessResult] = field(default_factory=list)

    def to_json(self) -> str:
        """轉為JSON格式"""
        data = {
            'total': self.total,
            'success': self.success,
            'failed': self.failed,
            'errors': self.errors,
            'processing_time': self.processing_time,
            'papers_added_to_kb': self.papers_added_to_kb,
            'zettel_generated': self.zettel_generated,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'results': [r.to_dict() for r in self.results]
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def to_report(self) -> str:
        """生成可讀報告"""
        lines = [
            "=" * 60,
            "📊 批次處理報告",
            "=" * 60,
            "",
            f"開始時間: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"結束時間: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"處理時間: {self.processing_time}",
            "",
            f"總文件數: {self.total}",
            f"✅ 成功: {self.success}",
            f"❌ 失敗: {self.failed}",
            f"成功率: {(self.success / self.total * 100):.1f}%" if self.total > 0 else "N/A",
            "",
            f"📚 加入知識庫: {self.papers_added_to_kb} 篇",
            f"🗂️  生成 Zettelkasten: {self.zettel_generated} 個",
            ""
        ]

        # 錯誤詳情
        if self.errors:
            lines.extend([
                "=" * 60,
                "❌ 錯誤詳情",
                "=" * 60,
                ""
            ])
            for i, error in enumerate(self.errors, 1):
                lines.append(f"{i}. {error['file']}")
                lines.append(f"   錯誤: {error['error']}")
                lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


class BatchProcessor:
    """
    批次處理器

    解決的核心問題:
    1. Windows 路徑編碼問題（空格、中文字符）
    2. UTF-8/GBK 編碼混合
    3. PDF 提取失敗的容錯處理
    4. 長時間處理的進度追蹤
    """

    def __init__(
        self,
        max_workers: int = 3,
        encoding: str = 'utf-8',
        error_handling: str = 'skip',
        project_root: Optional[str] = None
    ):
        """
        初始化批次處理器

        參數:
            max_workers: 平行處理的worker數量（建議2-4）
            encoding: 檔案系統編碼（Windows: utf-8）
            error_handling: 錯誤處理策略
                - skip: 跳過失敗的文件，繼續處理
                - retry: 重試失敗的文件（最多3次）
                - stop: 遇到錯誤立即停止
            project_root: 專案根目錄（預設為當前目錄）
        """
        self.max_workers = max_workers
        self.encoding = encoding
        self.error_handling = error_handling
        self.project_root = Path(project_root or os.getcwd())

        # 尋找核心腳本
        self.analyze_paper_script = self.project_root / "analyze_paper.py"
        self.make_slides_script = self.project_root / "make_slides.py"

        if not self.analyze_paper_script.exists():
            raise FileNotFoundError(f"找不到 analyze_paper.py: {self.analyze_paper_script}")

        if not self.make_slides_script.exists():
            raise FileNotFoundError(f"找不到 make_slides.py: {self.make_slides_script}")

    def process_batch(
        self,
        pdf_paths: Union[List[str], str],
        domain: str = "Research",
        add_to_kb: bool = True,
        generate_zettel: bool = True,
        zettel_config: Optional[dict] = None,
        progress_callback: Optional[Callable] = None
    ) -> BatchResult:
        """
        批次處理PDF文件

        參數:
            pdf_paths: PDF文件路徑列表，或包含PDF的資料夾路徑
            domain: 領域代碼（CogSci/Linguistics/AI等）
            add_to_kb: 是否加入知識庫
            generate_zettel: 是否生成Zettelkasten筆記
            zettel_config: Zettelkasten配置
                - detail_level: 詳細程度（standard/detailed/comprehensive）
                - card_count: 卡片數量（12/15/20）
                - llm_provider: LLM提供者（google/ollama/openai）
            progress_callback: 進度回調函數

        返回:
            BatchResult對象
        """
        # 初始化結果
        start_time = datetime.now()

        # 解析路徑
        if isinstance(pdf_paths, str):
            pdf_paths = self._find_pdfs(pdf_paths)

        # 驗證路徑
        valid_paths, invalid_paths = self.validate_paths(pdf_paths)

        print(f"\n{'='*60}")
        print(f"📦 批次處理器")
        print(f"{'='*60}\n")
        print(f"找到文件: {len(pdf_paths)} 個")
        print(f"✅ 有效: {len(valid_paths)} 個")
        if invalid_paths:
            print(f"❌ 無效: {len(invalid_paths)} 個")
        print(f"⚙️  工作執行緒: {self.max_workers}")
        print(f"📚 領域: {domain}")
        print(f"🗂️  加入知識庫: {'是' if add_to_kb else '否'}")
        print(f"📝 生成 Zettelkasten: {'是' if generate_zettel else '否'}")
        print("")

        # 初始化結果
        results = []
        success_count = 0
        failed_count = 0
        errors = []
        papers_added = 0
        zettel_generated = 0

        # 平行處理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任務
            future_to_path = {
                executor.submit(
                    self.process_single,
                    pdf_path,
                    domain=domain,
                    add_to_kb=add_to_kb,
                    generate_zettel=generate_zettel,
                    zettel_config=zettel_config
                ): pdf_path
                for pdf_path in valid_paths
            }

            # 處理完成的任務
            completed = 0
            for future in as_completed(future_to_path):
                pdf_path = future_to_path[future]
                completed += 1

                try:
                    result = future.result()
                    results.append(result)

                    if result.success:
                        success_count += 1
                        if result.paper_id:
                            papers_added += 1
                        if result.zettel_dir:
                            zettel_generated += 1

                        print(f"[{completed}/{len(valid_paths)}] ✅ {Path(result.file_path).name}")
                    else:
                        failed_count += 1
                        errors.append({
                            'file': result.file_path,
                            'error': result.error or "Unknown error"
                        })
                        print(f"[{completed}/{len(valid_paths)}] ❌ {Path(result.file_path).name}")
                        print(f"        錯誤: {result.error}")

                    # 進度回調
                    if progress_callback:
                        progress = (completed / len(valid_paths)) * 100
                        progress_callback(progress)

                except Exception as e:
                    failed_count += 1
                    errors.append({
                        'file': str(pdf_path),
                        'error': str(e)
                    })
                    print(f"[{completed}/{len(valid_paths)}] ❌ {Path(pdf_path).name}")
                    print(f"        異常: {e}")

        # 計算處理時間
        end_time = datetime.now()
        processing_time_delta = end_time - start_time
        processing_time_str = str(processing_time_delta).split('.')[0]  # 移除微秒

        # 創建結果
        batch_result = BatchResult(
            total=len(valid_paths),
            success=success_count,
            failed=failed_count,
            errors=errors,
            processing_time=processing_time_str,
            papers_added_to_kb=papers_added,
            zettel_generated=zettel_generated,
            start_time=start_time,
            end_time=end_time,
            results=results
        )

        return batch_result

    def validate_paths(self, paths: List[str]) -> Tuple[List[str], List[str]]:
        """
        驗證路徑有效性

        返回:
            (valid_paths, invalid_paths)
        """
        valid = []
        invalid = []

        for path_str in paths:
            path = Path(path_str)
            if path.exists() and path.is_file() and path.suffix.lower() == '.pdf':
                valid.append(str(path))
            else:
                invalid.append(str(path_str))

        return valid, invalid

    def process_single(
        self,
        pdf_path: str,
        domain: str = "Research",
        add_to_kb: bool = True,
        generate_zettel: bool = True,
        zettel_config: Optional[dict] = None
    ) -> ProcessResult:
        """
        處理單個PDF文件（內部方法）

        流程:
            1. 驗證文件存在性
            2. 調用 analyze_paper.py 分析PDF
            3. 如果 add_to_kb，加入知識庫
            4. 如果 generate_zettel，生成Zettelkasten
            5. 記錄處理結果
        """
        start_time = time.time()
        pdf_path_obj = Path(pdf_path)

        try:
            # 驗證文件存在
            if not pdf_path_obj.exists():
                return ProcessResult(
                    file_path=str(pdf_path),
                    success=False,
                    error=f"文件不存在: {pdf_path}",
                    processing_time=time.time() - start_time
                )

            paper_id = None
            zettel_dir = None
            zettel_imported = 0
            zettel_failed = 0

            # 步驟 1: 分析 PDF 並加入知識庫（如果需要）
            if add_to_kb:
                paper_id = self._analyze_and_add_to_kb(pdf_path_obj)

            # 步驟 2: 生成 Zettelkasten（如果需要）
            if generate_zettel:
                zettel_dir = self._generate_zettelkasten(
                    pdf_path_obj,
                    domain=domain,
                    paper_id=paper_id,
                    config=zettel_config
                )

                # ✅ 步驟 3: 導入 Zettelkasten 卡片到數據庫
                if zettel_dir and paper_id:
                    zettel_dir_path = Path(zettel_dir) if not isinstance(zettel_dir, Path) else zettel_dir

                    # 如果 zettel_dir 是字符串路徑，提取目錄名稱
                    if isinstance(zettel_dir, str):
                        # 從輸出中提取目錄（例如："output/zettelkasten_notes/zettel_XXX"）
                        import re
                        match = re.search(r'(output[/\\]zettelkasten_notes[/\\]zettel_[^/\\]+)', zettel_dir)
                        if match:
                            zettel_dir_path = Path(match.group(1))
                        else:
                            # 嘗試直接解析
                            parts = zettel_dir.split()
                            for part in parts:
                                if 'zettel_' in part:
                                    zettel_dir_path = Path(part.strip())
                                    break

                    if zettel_dir_path and zettel_dir_path.exists():
                        import_stats = self._import_zettel_to_kb(
                            zettel_dir_path,
                            paper_id,
                            domain
                        )
                        zettel_imported = import_stats.get('inserted', 0) + import_stats.get('duplicate', 0)
                        zettel_failed = import_stats.get('failed', 0)
                        print(f"  [DB] 已導入 {zettel_imported} 張卡片到數據庫（失敗: {zettel_failed}）")
                    else:
                        print(f"  [WARN] Zettelkasten 目錄不存在或無法解析: {zettel_dir}")

            processing_time = time.time() - start_time

            return ProcessResult(
                file_path=str(pdf_path),
                success=True,
                paper_id=paper_id,
                zettel_dir=zettel_dir,
                processing_time=processing_time,
                zettel_imported_to_db=zettel_imported,
                zettel_failed_import=zettel_failed
            )

        except Exception as e:
            processing_time = time.time() - start_time
            return ProcessResult(
                file_path=str(pdf_path),
                success=False,
                error=str(e),
                processing_time=processing_time
            )

    def _analyze_and_add_to_kb(self, pdf_path: Path) -> Optional[int]:
        """分析PDF並加入知識庫"""
        try:
            # 調用 analyze_paper.py
            cmd = [
                sys.executable,
                str(self.analyze_paper_script),
                str(pdf_path),
                '--add-to-kb'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300  # 5分鐘超時
            )

            if result.returncode != 0:
                raise RuntimeError(f"analyze_paper.py 失敗: {result.stderr}")

            # 嘗試從輸出中提取 paper_id
            # 輸出格式: "✅ 已加入知識庫 (ID: 123)"
            output = result.stdout
            if "(ID:" in output:
                id_str = output.split("(ID:")[1].split(")")[0].strip()
                return int(id_str)

            return None

        except Exception as e:
            raise RuntimeError(f"加入知識庫失敗: {e}")

    def _generate_zettelkasten(
        self,
        pdf_path: Path,
        domain: str = "Research",
        paper_id: Optional[int] = None,
        config: Optional[dict] = None
    ) -> Optional[str]:
        """生成 Zettelkasten 筆記"""
        try:
            # 預設配置
            if config is None:
                config = {}

            detail_level = config.get('detail_level', 'detailed')
            card_count = config.get('card_count', 20)
            llm_provider = config.get('llm_provider', 'google')
            model = config.get('model', None)

            # 構建命令
            cmd = [
                sys.executable,
                str(self.make_slides_script),
                pdf_path.stem,  # 使用文件名作為主題
                '--pdf', str(pdf_path),
                '--style', 'zettelkasten',
                '--detail', detail_level,
                '--slides', str(card_count),
                '--llm-provider', llm_provider,
                '--domain', domain
            ]

            # 如果指定了模型，添加 --model 參數
            if model:
                cmd.extend(['--model', model])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=600  # 10分鐘超時
            )

            if result.returncode != 0:
                raise RuntimeError(f"make_slides.py 失敗: {result.stderr}")

            # 嘗試從輸出中找到 zettel 目錄
            output = result.stdout
            if "zettel_" in output:
                # 簡單提取（實際可能需要更精確的解析）
                lines = output.split('\n')
                for line in lines:
                    if 'zettel_' in line and 'output' in line:
                        # 提取路徑
                        return line.strip()

            return None

        except Exception as e:
            raise RuntimeError(f"生成 Zettelkasten 失敗: {e}")

    def _import_zettel_to_kb(
        self,
        zettel_dir: Path,
        paper_id: int,
        domain: str
    ) -> Dict[str, int]:
        """
        導入 Zettelkasten 卡片到知識庫

        Args:
            zettel_dir: Zettelkasten 目錄路徑
            paper_id: 論文 ID
            domain: 領域代碼

        Returns:
            統計結果: {'imported': int, 'failed': int}
        """
        from claude_lit.knowledge_base import KnowledgeBaseManager

        kb = KnowledgeBaseManager()

        # 定位卡片目錄
        cards_dir = zettel_dir / 'zettel_cards'
        if not cards_dir.exists():
            print(f"  [WARN] 卡片目錄不存在: {cards_dir}")
            return {'imported': 0, 'failed': 0}

        # 獲取所有卡片文件
        card_files = list(cards_dir.glob('*.md'))
        if not card_files:
            print(f"  [WARN] 未找到卡片文件: {cards_dir}")
            return {'imported': 0, 'failed': 0}

        inserted = 0
        duplicate = 0
        failed = 0

        for card_file in card_files:
            try:
                # 使用 kb.parse_zettel_card() 解析
                card_data = kb.parse_zettel_card(str(card_file))

                if card_data:
                    # 導入到數據庫 - 使用結構化回傳
                    result = kb.add_zettel_card(card_data)

                    if result['status'] == 'inserted':
                        # 關聯到論文
                        kb.link_zettel_to_paper(result['card_id'], paper_id)
                        inserted += 1
                    elif result['status'] == 'duplicate':
                        # 重複卡片也嘗試關聯（可能是重新處理）
                        if result['card_id'] > 0:
                            kb.link_zettel_to_paper(result['card_id'], paper_id)
                        duplicate += 1
                        print(f"  [DUPLICATE] {card_file.name}: {result['message']}")
                    else:  # error
                        failed += 1
                        print(f"  [FAILED] {card_file.name}: {result['message']}")
                else:
                    failed += 1
                    print(f"  [WARN] 卡片解析失敗: {card_file.name}")

            except Exception as e:
                print(f"  [ERROR] 導入卡片時發生錯誤 ({card_file.name}): {e}")
                failed += 1

        return {'inserted': inserted, 'duplicate': duplicate, 'failed': failed}

    def _find_pdfs(self, path: str) -> List[str]:
        """
        尋找PDF文件

        支援:
        - 資料夾路徑: 返回資料夾中所有PDF文件
        - 單個PDF文件路徑: 返回包含該文件的列表

        參數:
            path: 資料夾路徑或PDF文件路徑

        返回:
            PDF文件路徑列表
        """
        path_obj = Path(path)

        if not path_obj.exists():
            return []

        # 如果是單個PDF文件
        if path_obj.is_file() and path_obj.suffix.lower() == '.pdf':
            return [str(path_obj)]

        # 如果是資料夾
        if path_obj.is_dir():
            pdf_files = list(path_obj.glob("*.pdf"))
            return [str(f) for f in pdf_files]

        return []

    def retry_failed(
        self,
        failed_files: List[str],
        max_retries: int = 3,
        **kwargs
    ) -> BatchResult:
        """
        重試失敗的文件

        參數:
            failed_files: 失敗的文件列表
            max_retries: 最大重試次數
            **kwargs: 傳遞給 process_batch 的其他參數
        """
        print(f"\n{'='*60}")
        print(f"🔄 重試失敗的文件")
        print(f"{'='*60}\n")
        print(f"文件數: {len(failed_files)}")
        print(f"最大重試次數: {max_retries}")
        print("")

        return self.process_batch(pdf_paths=failed_files, **kwargs)


if __name__ == "__main__":
    # 簡單測試
    print("BatchProcessor 模組載入成功")
    print(f"專案根目錄: {Path(__file__).parent.parent.parent}")
