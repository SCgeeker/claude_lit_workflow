# -*- coding: utf-8 -*-
"""claude_lit.resource_loader 測試（spec: cli — 資源解析順序）"""

from pathlib import Path

import pytest

from claude_lit.resource_loader import resolve_resource, use_overlay

REPO_ROOT = Path(__file__).parent.parent.parent

# 開發者維護的預設：repo 版與套件內建版須一致（發佈前同步，防漂移）
SYNCED_RESOURCES = [
    "templates/prompts/journal_club_template.jinja2",
    "templates/prompts/zettelkasten_template.jinja2",
    "templates/prompts/usage_guide.jinja2",
    "templates/prompts/media_slides_template.jinja2",
    "templates/prompts/media_zettel_template.jinja2",
    "templates/styles/academic_styles.yaml",
    "templates/styles/media_profiles.yaml",
    "templates/markdown/zettelkasten_card.jinja2",
    "templates/markdown/zettelkasten_index.jinja2",
    "config/settings.yaml",
    "config/model_selection.yaml",
]

# 使用者自訂檔：repo 版是使用者填入的領域術語，套件內建版是空白範本——
# 兩者本應不同，只驗證內建版存在且非空（供新安裝者 fallback）
USER_RESOURCES = [
    "config/custom_slides.md",
    "config/custom_zettel.md",
]


class TestResolveOrder:
    def test_explicit_wins(self, tmp_path):
        f = tmp_path / "my_template.jinja2"
        f.write_text("x", encoding="utf-8")
        assert resolve_resource("templates/prompts/journal_club_template.jinja2", explicit=f) == f

    def test_cwd_overrides_builtin(self, tmp_path, monkeypatch):
        override = tmp_path / "templates" / "prompts"
        override.mkdir(parents=True)
        f = override / "journal_club_template.jinja2"
        f.write_text("cwd 版本", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        resolved = resolve_resource("templates/prompts/journal_club_template.jinja2")
        assert resolved == f

    def test_builtin_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # 空目錄，無 cwd 覆蓋
        resolved = resolve_resource("templates/prompts/journal_club_template.jinja2")
        assert resolved.exists()
        assert "claude_lit" in str(resolved)

    def test_missing_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError):
            resolve_resource("templates/nonexistent.jinja2")


class TestOverlay:
    """per-job 覆蓋層（spec: cli — per-job 資源覆蓋層）"""

    REL = "templates/prompts/journal_club_template.jinja2"

    def _make(self, root: Path, text: str) -> Path:
        f = root / self.REL
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return f

    def test_overlay_beats_cwd(self, tmp_path, monkeypatch):
        self._make(tmp_path / "cwd", "cwd")
        overlay_file = self._make(tmp_path / "job", "job")
        monkeypatch.chdir(tmp_path / "cwd")
        with use_overlay(tmp_path / "job"):
            assert resolve_resource(self.REL) == overlay_file
        assert resolve_resource(self.REL) == tmp_path / "cwd" / self.REL  # 離開後恢復

    def test_overlay_missing_file_falls_through(self, tmp_path, monkeypatch):
        cwd_file = self._make(tmp_path / "cwd", "cwd")
        monkeypatch.chdir(tmp_path / "cwd")
        with use_overlay(tmp_path / "empty"):
            assert resolve_resource(self.REL) == cwd_file

    def test_explicit_still_wins(self, tmp_path):
        explicit = tmp_path / "x.jinja2"
        explicit.write_text("x", encoding="utf-8")
        with use_overlay(tmp_path):
            assert resolve_resource(self.REL, explicit=explicit) == explicit

    def test_threads_need_copied_context(self, tmp_path):
        import contextvars
        from concurrent.futures import ThreadPoolExecutor

        overlay_file = self._make(tmp_path / "job", "job")
        with ThreadPoolExecutor(max_workers=1) as pool, use_overlay(tmp_path / "job"):
            ctx = contextvars.copy_context()
            seen = pool.submit(ctx.run, resolve_resource, self.REL).result()
            plain = pool.submit(resolve_resource, self.REL).result()
        assert seen == overlay_file
        assert plain != overlay_file  # 未帶 context 的 worker 看不到 overlay


class TestBuiltinCompleteness:
    @pytest.mark.parametrize("relpath", SYNCED_RESOURCES)
    def test_synced_matches_repo(self, relpath, tmp_path, monkeypatch):
        """開發者維護的預設：套件內建版與 repo 版內容一致（防漂移）"""
        repo_file = REPO_ROOT / relpath
        monkeypatch.chdir(tmp_path)
        builtin = resolve_resource(relpath)
        assert builtin.exists()
        assert builtin.read_text(encoding="utf-8") == repo_file.read_text(encoding="utf-8")

    @pytest.mark.parametrize("relpath", USER_RESOURCES)
    def test_user_resource_builtin_exists(self, relpath, tmp_path, monkeypatch):
        """使用者自訂檔：只驗證套件內建範本存在且非空（不要求與 repo 版一致）"""
        monkeypatch.chdir(tmp_path)
        builtin = resolve_resource(relpath)
        assert builtin.exists()
        assert builtin.read_text(encoding="utf-8").strip()
