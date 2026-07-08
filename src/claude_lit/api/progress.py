# -*- coding: utf-8 -*-
"""進度回報事件

核心 API 以 ProgressEvent 回報進度，呈現層自行轉譯：
CLI 印成互動訊息、MCP 轉 progress notification。
"""

from typing import Callable, Optional

from pydantic import BaseModel

# 各階段代號：extract / prompt / cross_link / llm / parse / write / kb / embed
STAGES = ("extract", "prompt", "cross_link", "llm", "parse", "write", "kb", "embed")


class ProgressEvent(BaseModel):
    stage: str
    message: str
    current: Optional[int] = None
    total: Optional[int] = None


ProgressCallback = Callable[[ProgressEvent], None]
