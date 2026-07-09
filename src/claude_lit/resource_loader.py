# -*- coding: utf-8 -*-
"""資源解析

模板與預設設定的載入順序：
1. 明確傳入的路徑（explicit）
2. cwd 使用者檔（repo 內的 templates/、config/ 即此層；使用者可直接編輯）
3. 套件內建（claude_lit/resources/，隨 wheel 發佈）
"""

from importlib import resources
from pathlib import Path
from typing import Optional, Union


def resolve_resource(relpath: str, explicit: Optional[Union[str, Path]] = None) -> Path:
    """解析資源檔路徑。

    Args:
        relpath: 相對路徑（如 "templates/prompts/journal_club_template.jinja2"）
        explicit: 明確指定的路徑（最高優先）

    Returns:
        存在的檔案路徑

    Raises:
        FileNotFoundError: 三層皆找不到
    """
    if explicit:
        return Path(explicit)

    cwd_candidate = Path.cwd() / relpath
    if cwd_candidate.exists():
        return cwd_candidate

    builtin = resources.files("claude_lit") / "resources" / Path(relpath).as_posix()
    builtin_path = Path(str(builtin))
    if builtin_path.exists():
        return builtin_path

    raise FileNotFoundError(
        f"找不到資源：{relpath}（已檢查 cwd 與套件內建）"
    )
