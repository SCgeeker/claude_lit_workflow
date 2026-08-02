# -*- coding: utf-8 -*-
"""Zettel 卡片配額測試（P2：硬配額 → 上限 + fail-closed）

回歸缺陷 P2：模板以最強語氣命令「務必完整生成所有 N 張」，卻無任何退場條款，
概念不足時逼 LLM 杜撰/推斷填充湊數。改為：card_count 是「目標上限」而非硬目標，
並明列「寧缺勿造」的 fail-closed 條款。此為純 prompt 改動（卡片 ID 由程式決定性
重編，少出卡片安全）。
"""

from pathlib import Path

import claude_lit
from claude_lit.resource_loader import resolve_resource

_PKG_TEMPLATE = (
    Path(claude_lit.__file__).parent
    / "resources/templates/prompts/zettelkasten_template.jinja2"
)


def _both_templates():
    """cwd 覆蓋層 + 套件內建，兩份都必須一致地去掉硬配額語氣"""
    yield resolve_resource(
        "templates/prompts/zettelkasten_template.jinja2"
    ).read_text(encoding="utf-8")
    yield _PKG_TEMPLATE.read_text(encoding="utf-8")


def test_no_absolute_quota_command():
    for tpl in _both_templates():
        assert "務必完整生成所有" not in tpl
        assert "生成完整的 {{ card_count }} 張卡片" not in tpl


def test_has_upper_bound_and_fail_closed_clause():
    for tpl in _both_templates():
        assert "上限" in tpl          # card_count 定位為上限
        assert "寧可少出" in tpl      # fail-closed：寧缺勿造
        assert "嚴禁" in tpl          # 明令禁止杜撰/推斷湊數
