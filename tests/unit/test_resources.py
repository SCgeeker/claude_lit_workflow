# -*- coding: utf-8 -*-
"""claude_lit.resource_loader 測試（spec: cli — 資源解析順序）"""

from pathlib import Path

import pytest

from claude_lit.resource_loader import resolve_resource

REPO_ROOT = Path(__file__).parent.parent.parent

RESOURCES = [
    "templates/prompts/journal_club_template.jinja2",
    "templates/prompts/zettelkasten_template.jinja2",
    "templates/styles/academic_styles.yaml",
    "templates/markdown/zettelkasten_card.jinja2",
    "templates/markdown/zettelkasten_index.jinja2",
    "config/custom_slides.md",
    "config/custom_zettel.md",
    "config/settings.yaml",
    "config/model_selection.yaml",
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


class TestBuiltinCompleteness:
    @pytest.mark.parametrize("relpath", RESOURCES)
    def test_builtin_exists_and_matches_repo(self, relpath, tmp_path, monkeypatch):
        """套件內建資源存在，且與 repo 版本內容一致（防止兩份預設漂移）"""
        repo_file = REPO_ROOT / relpath
        monkeypatch.chdir(tmp_path)
        builtin = resolve_resource(relpath)
        assert builtin.exists()
        assert builtin.read_text(encoding="utf-8") == repo_file.read_text(encoding="utf-8")
