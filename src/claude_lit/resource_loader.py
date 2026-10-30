# -*- coding: utf-8 -*-
"""資源解析

模板與預設設定的載入順序：
1. 明確傳入的路徑（explicit）
2. overlay（以 contextvar 設定；網頁服務的 per-job 覆蓋檔，CLI 不使用）
3. cwd 使用者檔（repo 內的 templates/、config/ 即此層；使用者可直接編輯）
4. 套件內建（claude_lit/resources/，隨 wheel 發佈）

overlay 以 contextvar 傳遞而非 os.chdir：cwd 是行程內共用狀態，並行 job 互相干擾。
ThreadPoolExecutor 不會自動帶 context，提交時須用 contextvars.copy_context().run。
"""

import contextvars
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator, Optional, Union

_overlay_dir: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "claude_lit_resource_overlay", default=None
)


@contextmanager
def use_overlay(path: Optional[Union[str, Path]]) -> Iterator[None]:
    """在此 context 內以 path 作為最高優先（explicit 之後）的資源覆蓋層；None 表示不覆蓋。"""
    token = _overlay_dir.set(Path(path) if path else None)
    try:
        yield
    finally:
        _overlay_dir.reset(token)


def resolve_resource(relpath: str, explicit: Optional[Union[str, Path]] = None) -> Path:
    """解析資源檔路徑。

    Args:
        relpath: 相對路徑（如 "templates/prompts/journal_club_template.jinja2"）
        explicit: 明確指定的路徑（最高優先）

    Returns:
        存在的檔案路徑

    Raises:
        FileNotFoundError: 各層皆找不到
    """
    if explicit:
        return Path(explicit)

    overlay = _overlay_dir.get()
    if overlay is not None:
        overlay_candidate = overlay / relpath
        if overlay_candidate.exists():
            return overlay_candidate

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
