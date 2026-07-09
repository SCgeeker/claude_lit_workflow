#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作階段整理器
自動整理和清理工作過程產生的文件
"""

import os
import sys
import shutil
import yaml
import subprocess
import zipfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import glob

# 注意：庫模組不得在 import 時重新包裝 sys.stdout / sys.stderr
# （會關閉 pytest capture 與 MCP stdio 的底層串流）；編碼防護由 CLI 入口負責。


@dataclass
class CleanupReport:
    """清理報告"""
    session_date: str
    session_time: str
    session_type: str = "auto"

    # 整理的文件
    files_organized: Dict[str, List[str]] = field(default_factory=dict)

    # 刪除的文件
    files_deleted: List[str] = field(default_factory=list)

    # 備份信息
    backup_created: bool = False
    backup_path: str = ""

    # 統計
    total_moved: int = 0
    total_deleted: int = 0
    space_saved_bytes: int = 0

    # 知識庫統計
    total_papers: int = 0
    total_zettel_folders: int = 0
    total_slides: int = 0

    # Git 版本控制
    git_enabled: bool = False
    git_commit_created: bool = False
    git_commit_message: str = ""
    git_files_staged: List[str] = field(default_factory=list)

    # 歸檔壓縮
    archive_compressed: bool = False
    archive_files_count: int = 0
    archive_size_before: int = 0
    archive_size_after: int = 0
    archive_name: str = ""

    def space_saved_readable(self) -> str:
        """轉換為可讀的空間大小"""
        return self._format_bytes(self.space_saved_bytes)

    def _format_bytes(self, bytes_val: int) -> str:
        """格式化字節大小為可讀格式"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} TB"

    def to_markdown(self) -> str:
        """生成 Markdown 格式報告"""
        lines = [
            f"# 檔案清理報告 ({self.session_date})",
            "",
            f"**執行時間**: {self.session_date} {self.session_time}",
            f"**執行者**: Session Organizer (自動清理工具)",
            f"**工作階段類型**: {self.session_type}",
            "",
            "---",
            "",
            "## 清理執行摘要",
            "",
        ]

        # 統計摘要
        if self.total_moved > 0:
            lines.append(f"- ✅ **整理文件**: {self.total_moved} 個")
        if self.total_deleted > 0:
            lines.append(f"- 🗑️  **刪除文件**: {self.total_deleted} 個")
        if self.space_saved_bytes > 0:
            lines.append(f"- 💾 **節省空間**: {self.space_saved_readable()}")
        if self.backup_created:
            lines.append(f"- 📦 **備份創建**: {self.backup_path}")
        if self.git_commit_created:
            lines.append(f"- 🔄 **Git 提交**: {len(self.git_files_staged)} 個文件")
            lines.append(f"  - 提交訊息: `{self.git_commit_message}`")
        if self.archive_compressed:
            lines.append(f"- 📦 **歸檔壓縮**: {self.archive_files_count} 個文件")
            lines.append(f"  - 壓縮檔: `{self.archive_name}`")
            if self.archive_size_before > 0:
                saved = self.archive_size_before - self.archive_size_after
                lines.append(f"  - 壓縮節省: {self._format_bytes(saved)}")

        lines.extend(["", "---", ""])

        # 整理的文件
        if self.files_organized:
            lines.extend(["## 執行的整理動作", ""])

            for idx, (category, files) in enumerate(self.files_organized.items(), 1):
                if files:
                    lines.append(f"### {idx}. {category}")
                    lines.append(f"**文件數量**: {len(files)} 個")
                    lines.append("")

                    # 列出文件（最多顯示 10 個）
                    for file in files[:10]:
                        lines.append(f"- `{file}`")

                    if len(files) > 10:
                        lines.append(f"- ... (+{len(files) - 10} 個文件)")

                    lines.append("")

        # 刪除的文件
        if self.files_deleted:
            lines.extend(["## 清理的臨時文件", ""])
            lines.append(f"**刪除數量**: {len(self.files_deleted)} 個")
            lines.append("")

            for file in self.files_deleted[:10]:
                lines.append(f"- `{file}`")

            if len(self.files_deleted) > 10:
                lines.append(f"- ... (+{len(self.files_deleted) - 10} 個文件)")

            lines.append("")

        # 清理後狀態
        lines.extend(["---", "", "## 清理後狀態", ""])

        if self.total_papers > 0:
            lines.append(f"- 📚 **知識庫論文**: {self.total_papers} 篇")
        if self.total_zettel_folders > 0:
            lines.append(f"- 🗂️  **Zettelkasten 資料夾**: {self.total_zettel_folders} 個")
        if self.total_slides > 0:
            lines.append(f"- 📊 **簡報文件**: {self.total_slides} 個")

        # Git 狀態
        if self.git_enabled:
            lines.extend(["", "### Git 版本控制", ""])
            if self.git_commit_created:
                lines.append(f"- ✅ **已提交**: {len(self.git_files_staged)} 個文件")
                lines.append("")
                lines.append("**已提交的文件**:")
                for f in self.git_files_staged[:20]:  # 最多顯示20個
                    lines.append(f"  - `{f}`")
                if len(self.git_files_staged) > 20:
                    lines.append(f"  - ... (+{len(self.git_files_staged) - 20} 個文件)")
            else:
                lines.append("- ⚠️  **未提交**: Git commit 未執行")

        lines.extend(["", "---", ""])
        lines.append(f"**報告生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("**清理工具版本**: v1.1.0")

        return "\n".join(lines)


class SessionOrganizer:
    """
    工作階段整理器

    功能:
    1. 識別工作階段產生的文件
    2. 按規則分類和歸檔
    3. 刪除臨時文件
    4. 生成清理報告
    """

    def __init__(
        self,
        project_root: str = None,
        rules_file: str = None,
        dry_run: bool = True,
        auto_backup: bool = True,
        git_commit: bool = False,
        git_auto_stage: bool = True,
        rules_overrides: Dict = None
    ):
        """
        初始化整理器

        參數:
            project_root: 專案根目錄（預設為當前目錄）
            rules_file: 清理規則文件路徑
            dry_run: 乾跑模式（只顯示不執行）
            auto_backup: 自動備份
            git_commit: 是否自動提交到 Git
            git_auto_stage: 是否自動 stage 整理後的文件
            rules_overrides: 規則覆蓋設定
        """
        self.project_root = Path(project_root or os.getcwd())
        self.dry_run = dry_run
        self.auto_backup = auto_backup
        self.git_commit = git_commit
        self.git_auto_stage = git_auto_stage

        # 載入清理規則
        if rules_file is None:
            rules_file = self.project_root / "src" / "utils" / "cleanup_rules.yaml"

        self.rules = self._load_rules(rules_file)

        # 應用規則覆蓋
        if rules_overrides:
            for key, value in rules_overrides.items():
                if key in self.rules:
                    self.rules[key].update(value)
                else:
                    self.rules[key] = value

        # 初始化報告
        now = datetime.now()
        self.report = CleanupReport(
            session_date=now.strftime("%Y-%m-%d"),
            session_time=now.strftime("%H:%M:%S"),
            git_enabled=git_commit
        )

    def _load_rules(self, rules_file: Path) -> dict:
        """載入清理規則"""
        try:
            with open(rules_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️  無法載入清理規則: {e}")
            return {}

    def organize_session(
        self,
        session_type: str = 'auto'
    ) -> CleanupReport:
        """
        整理當前工作階段

        參數:
            session_type: 工作階段類型
                - auto: 自動檢測
                - batch: 批次處理
                - analysis: 論文分析
                - generation: 簡報/筆記生成
                - development: 開發文件整理
                - full: 完整清理（所有類型）

        返回:
            CleanupReport 對象
        """
        self.report.session_type = session_type

        print(f"\n{'='*60}")
        print(f"📁 檔案清理工具")
        print(f"{'='*60}\n")

        if self.dry_run:
            print("⚠️  乾跑模式: 只顯示會執行的動作，不實際執行")
            print("   使用 --execute 參數實際執行\n")

        # 1. 備份（如果啟用）
        if self.auto_backup and not self.dry_run:
            self._create_backup()

        # 2. 整理輸出文件
        self._organize_output_files()

        # 3. 清理臨時文件
        self._cleanup_temp_files()

        # 4. 壓縮歸檔（如果啟用）
        self._compress_old_archives()

        # 5. Git 版本控制（如果啟用）
        if self.git_commit and not self.dry_run:
            self._handle_git_commit()

        # 6. 更新統計
        self._update_statistics()

        # 6. 生成報告
        print(f"\n{'='*60}")
        print("📊 清理摘要")
        print(f"{'='*60}\n")
        print(f"✅ 整理文件: {self.report.total_moved} 個")
        print(f"🗑️  刪除文件: {self.report.total_deleted} 個")
        print(f"💾 節省空間: {self.report.space_saved_readable()}")
        if self.report.git_commit_created:
            print(f"🔄 Git 提交: {len(self.report.git_files_staged)} 個文件")

        return self.report

    def _create_backup(self):
        """創建備份"""
        print("📦 創建備份...")

        backup_settings = self.rules.get('backup', {})
        if not backup_settings.get('enabled', True):
            return

        backup_dir = self.project_root / backup_settings.get('backup_path', 'knowledge_base/backups')
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 備份資料庫
        db_path = self.project_root / "knowledge_base" / "index.db"
        if db_path.exists():
            backup_db = backup_dir / f"index_{timestamp}.db"
            shutil.copy2(db_path, backup_db)
            print(f"   ✅ 資料庫備份: {backup_db.name}")

            self.report.backup_created = True
            self.report.backup_path = str(backup_db.relative_to(self.project_root))

    def _organize_output_files(self):
        """整理輸出文件"""
        print("\n🗂️  整理輸出文件...")

        # 根據 session_type 決定要處理的規則
        if self.report.session_type == 'development':
            # 開發模式只處理開發文件
            org_rules = self.rules.get('development_organization', {})
        elif self.report.session_type == 'full':
            # 完整模式處理所有規則
            org_rules = {}
            org_rules.update(self.rules.get('output_organization', {}))
            org_rules.update(self.rules.get('development_organization', {}))
        else:
            # 預設只處理輸出文件
            org_rules = self.rules.get('output_organization', {})

        for category, rule in org_rules.items():
            patterns = rule.get('patterns', [])
            if isinstance(patterns, str):
                patterns = [patterns]

            destination = self.project_root / rule['destination']
            description = rule.get('description', category)
            exclude_patterns = rule.get('exclude', [])

            files_to_move = []

            # 查找匹配的文件
            for pattern in patterns:
                for file_path in self.project_root.glob(pattern):
                    # 檢查排除規則
                    should_exclude = False
                    for exclude_pattern in exclude_patterns:
                        if file_path.match(exclude_pattern):
                            should_exclude = True
                            break

                    if not should_exclude and file_path.exists():
                        files_to_move.append(file_path)

            # 移動文件
            if files_to_move:
                print(f"\n   📋 {description}")
                print(f"   目標: {destination.relative_to(self.project_root)}")

                if not self.dry_run:
                    destination.mkdir(parents=True, exist_ok=True)

                moved_files = []
                for file_path in files_to_move:
                    rel_path = file_path.relative_to(self.project_root)
                    print(f"      • {rel_path}")

                    if not self.dry_run:
                        try:
                            target = destination / file_path.name
                            # 如果目標已存在，添加時間戳
                            if target.exists():
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                stem = target.stem
                                suffix = target.suffix
                                target = destination / f"{stem}_{timestamp}{suffix}"

                            shutil.move(str(file_path), str(target))
                            moved_files.append(str(rel_path))
                            self.report.total_moved += 1
                        except Exception as e:
                            print(f"      ⚠️  移動失敗: {e}")
                    else:
                        moved_files.append(str(rel_path))

                if moved_files:
                    self.report.files_organized[description] = moved_files

                print(f"   ✅ {len(moved_files)} 個文件")

    def _cleanup_temp_files(self):
        """清理臨時文件"""
        print("\n🧹 清理臨時文件...")

        temp_rules = self.rules.get('temp_files', {})
        protected_patterns = self.rules.get('safety', {}).get('protected_patterns', [])

        for category, rule in temp_rules.items():
            patterns = rule.get('patterns', [])
            if isinstance(patterns, str):
                patterns = [patterns]

            description = rule.get('description', category)

            files_to_delete = []

            # 查找匹配的文件
            for pattern in patterns:
                # 跳過通配符 "*" 用於根目錄的情況
                if pattern == "*" and category == "empty_files":
                    # 特殊處理：只檢查根目錄的文件（不含子目錄）
                    for file_path in self.project_root.iterdir():
                        if file_path.is_file() and self._should_delete(file_path, rule.get('conditions', {})):
                            if not self._is_protected(file_path, protected_patterns):
                                files_to_delete.append(file_path)
                else:
                    for file_path in self.project_root.glob(pattern):
                        if file_path.exists():
                            # 檢查是否受保護
                            if self._is_protected(file_path, protected_patterns):
                                continue

                            # 檢查條件（如文件大小、修改時間等）
                            if self._should_delete(file_path, rule.get('conditions', {})):
                                files_to_delete.append(file_path)

            # 刪除文件
            if files_to_delete:
                print(f"\n   🗑️  {description}")

                for file_path in files_to_delete:
                    rel_path = file_path.relative_to(self.project_root)
                    file_size = file_path.stat().st_size if file_path.is_file() else 0

                    print(f"      • {rel_path}")

                    if not self.dry_run:
                        try:
                            if file_path.is_dir():
                                shutil.rmtree(file_path)
                            else:
                                file_path.unlink()

                            self.report.files_deleted.append(str(rel_path))
                            self.report.total_deleted += 1
                            self.report.space_saved_bytes += file_size
                        except Exception as e:
                            print(f"      ⚠️  刪除失敗: {e}")
                    else:
                        self.report.files_deleted.append(str(rel_path))

                print(f"   ✅ {len(files_to_delete)} 個文件")

    def _should_delete(self, file_path: Path, conditions: dict) -> bool:
        """檢查是否應該刪除文件"""
        # 不刪除目錄（只在明確指定時才刪除）
        if file_path.is_dir():
            return False

        # 檢查文件大小
        max_size_kb = conditions.get('max_size_kb')
        if max_size_kb is not None:
            if file_path.is_file():
                size_kb = file_path.stat().st_size / 1024
                if size_kb > max_size_kb:
                    return False

        # 檢查文件年齡
        min_age_hours = conditions.get('min_age_hours')
        if min_age_hours is not None:
            age_hours = (datetime.now().timestamp() - file_path.stat().st_mtime) / 3600
            if age_hours < min_age_hours:
                return False

        return True

    def _is_protected(self, file_path: Path, protected_patterns: list) -> bool:
        """檢查文件是否受保護"""
        rel_path = file_path.relative_to(self.project_root)

        for pattern in protected_patterns:
            # 檢查完整路徑匹配
            if rel_path.match(pattern):
                return True

            # 檢查文件名匹配
            if file_path.name.endswith(pattern.replace('*', '')):
                return True

        return False

    def _update_statistics(self):
        """更新統計信息"""
        # 統計論文數
        papers_dir = self.project_root / "knowledge_base" / "papers"
        if papers_dir.exists():
            self.report.total_papers = len(list(papers_dir.glob("*.md")))

        # 統計 Zettelkasten 資料夾
        zettel_dir = self.project_root / "output" / "zettelkasten_notes"
        if zettel_dir.exists():
            self.report.total_zettel_folders = len([d for d in zettel_dir.iterdir() if d.is_dir()])

        # 統計簡報文件
        slides_dir = self.project_root / "output" / "slides"
        if slides_dir.exists():
            pptx_files = list(slides_dir.glob("*.pptx"))
            md_files = list(slides_dir.glob("*_slides.md"))
            self.report.total_slides = len(pptx_files) + len(md_files)

    def _is_git_repository(self) -> bool:
        """檢查是否為 Git 倉庫"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_git_status(self) -> Dict[str, List[str]]:
        """
        獲取 Git 狀態

        返回:
            {
                'modified': [...],
                'deleted': [...],
                'untracked': [...],
                'staged': [...]
            }
        """
        if not self._is_git_repository():
            return {}

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )

            status = {
                'modified': [],
                'deleted': [],
                'untracked': [],
                'staged': []
            }

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                # Git status --porcelain 格式: XY filename
                # X 是 index 狀態，Y 是 working tree 狀態
                xy = line[:2]
                filepath = line[3:].strip()

                if xy[0] in ['M', 'A', 'D', 'R', 'C']:
                    status['staged'].append(filepath)

                if xy[1] == 'M' or xy == ' M':
                    status['modified'].append(filepath)
                elif xy[1] == 'D' or xy == ' D':
                    status['deleted'].append(filepath)
                elif xy == '??':
                    status['untracked'].append(filepath)

            return status

        except Exception as e:
            print(f"⚠️  獲取 Git 狀態失敗: {e}")
            return {}

    def _compress_old_archives(self):
        """壓縮舊的歸檔文件"""
        compression_config = self.rules.get('archive_compression', {})

        if not compression_config.get('enabled', True):
            return

        compress_after_days = compression_config.get('compress_after_days', 7)
        archive_dir = self.project_root / compression_config.get('archive_directory', 'archive')

        if not archive_dir.exists():
            return

        print("\n📦 檢查歸檔文件...")

        # 計算日期閾值
        cutoff_date = datetime.now() - timedelta(days=compress_after_days)

        # 收集需要壓縮的文件
        files_to_compress = []
        total_size = 0
        exclude_patterns = compression_config.get('exclude_patterns', [])

        for file_path in archive_dir.rglob('*'):
            if file_path.is_file():
                # 檢查是否應該排除
                should_exclude = False
                for pattern in exclude_patterns:
                    if file_path.match(pattern):
                        should_exclude = True
                        break

                if should_exclude:
                    continue

                # 檢查修改時間
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff_date:
                    files_to_compress.append(file_path)
                    total_size += file_path.stat().st_size

        if not files_to_compress:
            print("   ✓ 沒有需要壓縮的舊文件")
            return

        print(f"   找到 {len(files_to_compress)} 個超過 {compress_after_days} 天的文件")
        print(f"   總大小: {self.report._format_bytes(total_size)}")

        if self.dry_run:
            print("   [乾跑模式] 將壓縮以下文件:")
            for file_path in files_to_compress[:10]:  # 只顯示前10個
                rel_path = file_path.relative_to(self.project_root)
                print(f"      • {rel_path}")
            if len(files_to_compress) > 10:
                print(f"      ... 還有 {len(files_to_compress) - 10} 個文件")
            return

        # 生成壓縮檔名稱
        date_str = datetime.now().strftime("%Y%m%d")
        archive_name = compression_config.get('compressed_archive_name', 'archived_{date}.zip')
        archive_name = archive_name.replace('{date}', date_str)
        archive_path = archive_dir / archive_name

        # 如果檔案已存在，添加時間戳
        if archive_path.exists():
            timestamp = datetime.now().strftime("%H%M%S")
            archive_name = archive_name.replace('.zip', f'_{timestamp}.zip')
            archive_path = archive_dir / archive_name

        try:
            print(f"   壓縮中: {archive_name}")

            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in files_to_compress:
                    # 計算相對路徑
                    if compression_config.get('keep_structure', True):
                        # 保持目錄結構
                        arcname = file_path.relative_to(archive_dir)
                    else:
                        # 平鋪所有文件
                        arcname = file_path.name

                    zipf.write(file_path, arcname)

            # 獲取壓縮後的大小
            compressed_size = archive_path.stat().st_size

            # 更新報告
            self.report.archive_compressed = True
            self.report.archive_files_count = len(files_to_compress)
            self.report.archive_size_before = total_size
            self.report.archive_size_after = compressed_size
            self.report.archive_name = archive_name

            print(f"   ✅ 壓縮完成")
            print(f"      壓縮比: {((total_size - compressed_size) / total_size * 100):.1f}%")

            # 刪除原文件（如果設定）
            if compression_config.get('delete_after_compress', True):
                print("   刪除已壓縮的文件...")
                for file_path in files_to_compress:
                    try:
                        file_path.unlink()
                    except Exception as e:
                        print(f"      ⚠️ 無法刪除 {file_path.name}: {e}")

                # 刪除空目錄
                for dir_path in sorted(archive_dir.rglob('*'), reverse=True):
                    if dir_path.is_dir() and not any(dir_path.iterdir()):
                        try:
                            dir_path.rmdir()
                        except:
                            pass

                print("   ✅ 已刪除原文件")

        except Exception as e:
            print(f"   ❌ 壓縮失敗: {e}")

    def _handle_git_commit(self):
        """處理 Git 提交"""
        print("\n🔄 處理 Git 版本控制...")

        if not self._is_git_repository():
            print("   ⚠️  不是 Git 倉庫，跳過版本控制")
            return

        # 獲取 Git 狀態
        git_status = self._get_git_status()

        files_to_stage = []

        # 1. 自動 stage 新增的知識庫論文
        kb_papers = [f for f in git_status.get('untracked', [])
                    if f.startswith('knowledge_base/papers/') and f.endswith('.md')]
        files_to_stage.extend(kb_papers)

        # 2. 自動 stage 新增的 output 目錄
        output_dirs = [f for f in git_status.get('untracked', [])
                      if f.startswith('output/')]
        files_to_stage.extend(output_dirs)

        # 3. 自動 stage 已刪除的文件
        files_to_stage.extend(git_status.get('deleted', []))

        # 4. 自動 stage 修改的配置文件
        modified_configs = [f for f in git_status.get('modified', [])
                           if f.endswith(('.yaml', '.json', 'settings.local.json'))]
        files_to_stage.extend(modified_configs)

        if not files_to_stage:
            print("   ℹ️  沒有需要提交的文件")
            return

        print(f"   📝 準備提交 {len(files_to_stage)} 個文件...")

        # Stage 文件
        staged_files = []
        for filepath in files_to_stage:
            try:
                subprocess.run(
                    ["git", "add", filepath],
                    cwd=self.project_root,
                    check=True,
                    capture_output=True,
                    timeout=10
                )
                staged_files.append(filepath)
                print(f"      ✅ {filepath}")
            except Exception as e:
                print(f"      ⚠️  無法 stage {filepath}: {e}")

        if not staged_files:
            print("   ⚠️  沒有成功 stage 任何文件")
            return

        # 生成提交訊息
        commit_message = self._generate_commit_message(staged_files, git_status)

        # 執行 commit
        try:
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.project_root,
                check=True,
                capture_output=True,
                timeout=30
            )

            self.report.git_commit_created = True
            self.report.git_commit_message = commit_message.split('\n')[0]  # 只取第一行
            self.report.git_files_staged = staged_files

            print(f"\n   ✅ Git 提交成功")
            print(f"      訊息: {self.report.git_commit_message}")

        except subprocess.CalledProcessError as e:
            print(f"   ❌ Git 提交失敗: {e}")
            print(f"      輸出: {e.stderr.decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"   ❌ Git 提交失敗: {e}")

    def _generate_commit_message(self, staged_files: List[str], git_status: Dict) -> str:
        """
        生成 Git 提交訊息

        參數:
            staged_files: 已 stage 的文件列表
            git_status: Git 狀態字典

        返回:
            提交訊息字串
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 分類文件
        papers = [f for f in staged_files if 'knowledge_base/papers/' in f]
        outputs = [f for f in staged_files if f.startswith('output/')]
        configs = [f for f in staged_files if f.endswith(('.yaml', '.json'))]
        deleted = [f for f in staged_files if f in git_status.get('deleted', [])]

        # 構建提交訊息
        lines = ["Cleanup session: Organize files and update knowledge base"]
        lines.append("")

        if papers:
            lines.append(f"- Add {len(papers)} paper(s) to knowledge base")

        if outputs:
            # 統計不同類型的output
            slides = len([f for f in outputs if 'slides' in f])
            zettel = len([f for f in outputs if 'zettelkasten' in f])
            analysis = len([f for f in outputs if 'analysis' in f])

            if slides:
                lines.append(f"- Add {slides} slide file(s)")
            if zettel:
                lines.append(f"- Add {zettel} zettelkasten folder(s)")
            if analysis:
                lines.append(f"- Add {analysis} analysis file(s)")

        if deleted:
            lines.append(f"- Remove {len(deleted)} deleted file(s)")

        if configs:
            lines.append(f"- Update configuration file(s)")

        lines.append("")
        lines.append(f"🤖 Generated by Session Organizer")
        lines.append(f"📅 {timestamp}")

        return "\n".join(lines)

    def save_report(self, output_path: str = None) -> str:
        """
        保存清理報告

        參數:
            output_path: 輸出路徑（預設自動生成）

        返回:
            報告文件路徑
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.project_root / f"FILE_CLEANUP_REPORT_{timestamp}.md"
        else:
            output_path = Path(output_path)

        report_content = self.report.to_markdown()

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        print(f"\n📄 報告已保存: {output_path.name}")

        return str(output_path)


if __name__ == "__main__":
    # 簡單測試
    organizer = SessionOrganizer(dry_run=True)
    report = organizer.organize_session()
    organizer.save_report()
