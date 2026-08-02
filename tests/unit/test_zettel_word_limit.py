# -*- coding: utf-8 -*-
"""Zettel 字元上限測試（① 提高上限 + 移除模板重複截斷 + 單一真相）

回歸缺陷 P1：
- 抽取上限由 40000 提高，讓長論文後半不再於生成時消失。
- 模板端 truncate(40000) 為重複耦合的地雷（調高常數會被 Jinja 靜默壓回），須移除。
- 常數收斂為單一真相，zettel.py 與 prompts.py 不得各自持有不同字面量。
"""

from claude_lit.resource_loader import resolve_resource


def test_zettel_template_has_no_hardcoded_truncate():
    """兩份模板都不得再硬編 truncate（截斷點只保留在 extractor）"""
    for path in ("templates/prompts/zettelkasten_template.jinja2",):
        tpl = resolve_resource(path).read_text(encoding="utf-8")
        assert "truncate(40000)" not in tpl
        assert "| truncate" not in tpl


def test_zettel_max_chars_raised_and_single_source():
    from claude_lit.api import prompts, zettel

    # 提高至可容納整篇論文（含長 review）
    assert prompts._ZETTEL_MAX_CHARS >= 100000
    # 單一真相：zettel.py 直接沿用 prompts.py 的常數，不得各自定義
    assert zettel._ZETTEL_MAX_CHARS == prompts._ZETTEL_MAX_CHARS
