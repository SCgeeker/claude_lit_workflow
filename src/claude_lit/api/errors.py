# -*- coding: utf-8 -*-
"""核心 API 例外階層

所有 API 層錯誤以 LitWorkflowError 子類拋出，附 hint 修復建議。
CLI 層 catch 後印出訊息與 hint；MCP 層轉為 isError=true 的 tool result。
"""

from typing import Optional


class LitWorkflowError(Exception):
    """API 層錯誤基底。

    Args:
        message: 錯誤描述
        hint: 給使用者的修復建議（可選）
    """

    def __init__(self, message: str, *, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint


class SourceNotFoundError(LitWorkflowError):
    """內容來源不存在（PDF / URL / 知識庫論文）"""


class ExtractionError(LitWorkflowError):
    """內容抽取失敗（PDF 解析、URL 抓取）"""


class CiteKeyMissingError(LitWorkflowError):
    """無法解析 cite_key"""


class ProviderUnavailableError(LitWorkflowError):
    """無可用的 LLM 供應商"""


class LLMGenerationError(LitWorkflowError):
    """LLM 呼叫失敗或輸出無法解析"""


class ConfigError(LitWorkflowError):
    """設定檔或環境設定錯誤"""
