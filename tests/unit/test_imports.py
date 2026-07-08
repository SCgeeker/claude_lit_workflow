# -*- coding: utf-8 -*-
"""package 佈局健全性測試（spec: cli）"""

import importlib
from pathlib import Path

import pytest

SRC_PKG = Path(__file__).parent.parent.parent / "src" / "claude_lit"

CORE_MODULES = [
    "claude_lit",
    "claude_lit.resource_loader",
    "claude_lit.api",
    "claude_lit.api.models",
    "claude_lit.api.errors",
    "claude_lit.api.progress",
    "claude_lit.api.sources",
    "claude_lit.api.slides",
    "claude_lit.api.zettel",
    "claude_lit.api.providers",
    "claude_lit.api.prompts",
    "claude_lit.generators",
    "claude_lit.generators.slide_maker",
    "claude_lit.generators.zettel_maker",
    "claude_lit.extractors",
    "claude_lit.extractors.pdf_extractor",
    "claude_lit.extractors.url_extractor",
    "claude_lit.utils.config_loader",
    "claude_lit.utils.logger",
    "claude_lit.utils.prompt_loader",
    "claude_lit.knowledge_base",
    "claude_lit.mcp_server.server",
    "claude_lit.mcp_server.__main__",
    "claude_lit.cli.slides",
    "claude_lit.cli.zettel",
    "claude_lit.cli.setup_check",
]


class TestImports:
    @pytest.mark.parametrize("module", CORE_MODULES)
    def test_core_module_importable(self, module):
        importlib.import_module(module)

    def test_no_sys_path_insert_in_package(self):
        offenders = []
        for py in SRC_PKG.rglob("*.py"):
            if "resources" in py.parts:
                continue
            if "sys.path.insert" in py.read_text(encoding="utf-8"):
                offenders.append(str(py.relative_to(SRC_PKG)))
        assert offenders == []

    def test_no_src_prefix_imports(self):
        """不得殘留 from src. / import src. 舊寫法"""
        offenders = []
        for py in SRC_PKG.rglob("*.py"):
            if "resources" in py.parts:
                continue
            text = py.read_text(encoding="utf-8")
            if "from src." in text or "import src." in text:
                offenders.append(str(py.relative_to(SRC_PKG)))
        assert offenders == []
