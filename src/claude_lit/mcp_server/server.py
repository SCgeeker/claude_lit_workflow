# -*- coding: utf-8 -*-
"""claude-lit-workflow MCP server

基於官方 MCP Python SDK（FastMCP）。三類 primitive：
- Tools：generate_slides / generate_zettel / check_setup / list_options / read_output
- Resources：prompt 模板、風格目錄、自訂需求檔、脫敏設定
- Prompts：slides-prompt / zettel-prompt（渲染完成的提示詞，供呼叫端 LLM 自行生成）

生成模式為「伺服器端生成」：工具內部沿用核心 API 呼叫已設定的 LLM；
API key 只存在伺服器行程，不經協定傳輸。
"""

import logging
from pathlib import Path
from typing import Optional

import anyio
import yaml
from mcp.server.fastmcp import Context, FastMCP

from claude_lit.api import check_providers as api_check_providers
from claude_lit.api import list_options as api_list_options
from claude_lit.api.errors import LitWorkflowError
from claude_lit.api.models import (
    OptionCatalog,
    ProviderReport,
    SlideRequest,
    SlideResult,
    ZettelRequest,
    ZettelResult,
)
from claude_lit.api.progress import ProgressEvent
from claude_lit.api.prompts import render_slides_prompt, render_zettel_prompt
from claude_lit.api.slides import generate_slides as api_generate_slides
from claude_lit.api.zettel import generate_zettel as api_generate_zettel
from claude_lit.utils.config_loader import load_env_file

logger = logging.getLogger("claude_lit_workflow.mcp_server")

from claude_lit.resource_loader import resolve_resource

# 生成輸出以啟動時的工作目錄為基準（與 CLI 行為一致）
OUTPUT_DIR = Path.cwd() / "output"


def _read_resource_file(relpath: str, fallback: Optional[str] = None) -> str:
    try:
        return resolve_resource(relpath).read_text(encoding="utf-8")
    except FileNotFoundError:
        if fallback is not None:
            return fallback
        raise

# 伺服器行程啟動時載入 .env（金鑰只存在於此行程）
load_env_file()

mcp = FastMCP(
    "claude-lit-workflow",
    instructions=(
        "學術文獻工作流工具：從 PDF / URL / 主題生成學術投影片（Markdown/PPTX）"
        "與 Zettelkasten 原子卡片。生成由伺服器端已設定的 LLM 完成，"
        "長時工具（generate_slides / generate_zettel）可能需要數分鐘，"
        "會透過 progress notification 回報進度。"
        "若要由呼叫端 LLM 自行生成，改用 slides-prompt / zettel-prompt 取得完整提示詞。"
    ),
)


# ── 內部工具 ─────────────────────────────────────────────────────────────────


def _wrap_error(e: LitWorkflowError) -> Exception:
    msg = str(e)
    if e.hint:
        msg = f"{msg}（提示：{e.hint}）"
    return RuntimeError(msg)


async def _run_generation(api_fn, request, ctx: Optional[Context]):
    """在 worker thread 執行同步核心 API，橋接 ProgressEvent → MCP progress notification。"""
    counter = {"n": 0}

    def progress_cb(ev: ProgressEvent):
        counter["n"] += 1
        if ctx is None:
            return
        try:
            anyio.from_thread.run(
                ctx.report_progress, float(counter["n"]), None, f"[{ev.stage}] {ev.message}"
            )
        except Exception as exc:  # 通知失敗不中斷生成
            logger.debug("progress notification 失敗：%s", exc)

    try:
        return await anyio.to_thread.run_sync(lambda: api_fn(request, progress=progress_cb))
    except LitWorkflowError as e:
        raise _wrap_error(e) from e


# ── Tools ────────────────────────────────────────────────────────────────────


@mcp.tool()
async def generate_slides(
    topic: Optional[str] = None,
    pdf: Optional[str] = None,
    url: Optional[str] = None,
    style: str = "modern_academic",
    detail: str = "standard",
    language: str = "chinese",
    slide_count: int = 15,
    output_format: str = "markdown",
    output_path: Optional[str] = None,
    provider: str = "auto",
    model: Optional[str] = None,
    custom_requirements: Optional[str] = None,
    ctx: Context = None,
) -> SlideResult:
    """從主題、PDF 或 URL 生成學術投影片。

    來源三選一（至少提供 topic、pdf 或 url 其中一項；pdf 與 url 互斥）。
    style 七選一（見 list_options）；output_format：markdown / pptx / both。
    回傳輸出檔案的絕對路徑清單與 metadata；檔案內容可用 read_output 讀取。
    """
    request = SlideRequest(
        topic=topic,
        pdf=pdf,
        url=url,
        style=style,
        detail=detail,
        language=language,
        slide_count=slide_count,
        output_format=output_format,
        output_path=output_path,
        provider=provider,
        model=model,
        custom_requirements=custom_requirements,
    )
    return await _run_generation(api_generate_slides, request, ctx)


@mcp.tool()
async def generate_zettel(
    pdf: Optional[str] = None,
    url: Optional[str] = None,
    detail: str = "standard",
    language: str = "chinese",
    domain: str = "Research",
    cite_key: Optional[str] = None,
    custom_requirements: Optional[str] = None,
    add_to_kb: bool = False,
    cross_link: bool = False,
    ground: bool = True,
    output_dir: Optional[str] = None,
    provider: str = "auto",
    model: Optional[str] = None,
    ctx: Context = None,
) -> ZettelResult:
    """從 PDF 或 URL 生成 Zettelkasten 原子卡片（pdf 與 url 擇一）。

    detail 決定卡片數（standard=12、comprehensive=30+，見 list_options）。
    add_to_kb 預設 False（不寫入伺服器本機知識庫）。
    ground 預設 True：驗證每張卡片的核心可逐字回溯原文，定位不到則抹除、
    中文定位不到則隔離待審；設 False 可關閉。
    回傳卡片檔案路徑清單與 metadata；卡片內容可用 read_output 讀取。
    """
    request = ZettelRequest(
        pdf=pdf,
        url=url,
        detail=detail,
        language=language,
        domain=domain,
        cite_key=cite_key,
        custom_requirements=custom_requirements,
        add_to_kb=add_to_kb,
        cross_link=cross_link,
        ground=ground,
        output_dir=output_dir,
        provider=provider,
        model=model,
    )
    return await _run_generation(api_generate_zettel, request, ctx)


@mcp.tool()
def check_setup() -> ProviderReport:
    """檢查伺服器端各 LLM 供應商（Google/OpenAI/Anthropic/Ollama）的連線狀態與建議供應商。"""
    return api_check_providers()


@mcp.tool()
def list_options() -> OptionCatalog:
    """列出投影片風格（7 種）、詳細程度（5 種）、語言模式（3 種）的完整目錄與說明。"""
    return api_list_options()


@mcp.tool()
def read_output(path: str, max_chars: int = 20000) -> str:
    """讀取 output/ 目錄下的生成結果檔案（供無檔案系統存取權的遠端 client 使用）。

    path 可為相對於 output/ 的路徑或其下的絕對路徑；超出 output/ 的路徑一律拒絕。
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = OUTPUT_DIR / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(OUTPUT_DIR.resolve()):
        raise PermissionError(f"僅允許讀取 output/ 目錄下的檔案：{path}")
    if not resolved.is_file():
        raise FileNotFoundError(f"找不到檔案：{path}")
    text = resolved.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n…（已截斷，全文 {len(text)} 字元）"
    return text


# ── Resources ────────────────────────────────────────────────────────────────


@mcp.resource("template://prompts/journal-club", mime_type="text/plain")
def journal_club_template() -> str:
    """投影片生成的原始 jinja2 prompt 模板"""
    return _read_resource_file("templates/prompts/journal_club_template.jinja2")


@mcp.resource("template://prompts/zettelkasten", mime_type="text/plain")
def zettelkasten_template() -> str:
    """Zettel 卡片生成的原始 jinja2 prompt 模板"""
    return _read_resource_file("templates/prompts/zettelkasten_template.jinja2")


@mcp.resource("styles://academic-styles", mime_type="application/yaml")
def academic_styles() -> str:
    """8 種學術風格、5 種詳細程度、3 種語言的完整定義"""
    return _read_resource_file("templates/styles/academic_styles.yaml")


@mcp.resource("config://custom-slides", mime_type="text/markdown")
def custom_slides() -> str:
    """投影片生成的使用者自訂需求"""
    return _read_resource_file("config/custom_slides.md", fallback="（未設定自訂需求）")


@mcp.resource("config://custom-zettel", mime_type="text/markdown")
def custom_zettel() -> str:
    """Zettel 卡片生成的使用者自訂需求"""
    return _read_resource_file("config/custom_zettel.md", fallback="（未設定自訂需求）")


@mcp.resource("config://settings", mime_type="application/yaml")
def sanitized_settings() -> str:
    """伺服器目前設定（脫敏：只含白名單欄位，不含任何金鑰）"""
    raw = yaml.safe_load(_read_resource_file("config/settings.yaml", fallback="{}")) or {}
    llm = raw.get("llm", {}) or {}
    sanitized = {
        "pdf": raw.get("pdf", {}),
        "llm": {
            "default_provider": llm.get("default_provider"),
            "google_model": (llm.get("google") or {}).get("model"),
            "ollama_model": (llm.get("ollama") or {}).get("model"),
        },
    }
    return yaml.safe_dump(sanitized, allow_unicode=True, sort_keys=False)


# ── Prompts ──────────────────────────────────────────────────────────────────


@mcp.prompt(name="slides-prompt")
def slides_prompt(
    topic: Optional[str] = None,
    pdf_path: Optional[str] = None,
    url: Optional[str] = None,
    style: str = "modern_academic",
    detail: str = "standard",
    language: str = "chinese",
    slide_count: int = 15,
) -> str:
    """取得投影片生成的完整提示詞（伺服器端抽取來源並渲染模板），供呼叫端 LLM 自行生成。"""
    request = SlideRequest(
        topic=topic,
        pdf=pdf_path,
        url=url,
        style=style,
        detail=detail,
        language=language,
        slide_count=int(slide_count),
    )
    return render_slides_prompt(request)


@mcp.prompt(name="zettel-prompt")
def zettel_prompt(
    pdf_path: Optional[str] = None,
    url: Optional[str] = None,
    detail: str = "standard",
    language: str = "chinese",
    domain: str = "Research",
    cite_key: Optional[str] = None,
) -> str:
    """取得 Zettel 卡片生成的完整提示詞（伺服器端抽取來源並渲染模板），供呼叫端 LLM 自行生成。"""
    request = ZettelRequest(
        pdf=pdf_path,
        url=url,
        detail=detail,
        language=language,
        domain=domain,
        cite_key=cite_key,
        add_to_kb=False,
    )
    return render_zettel_prompt(request)
