# -*- coding: utf-8 -*-
"""MCP server 測試（spec: mcp-server）

以官方 SDK 的 in-memory session 測試，不需真實 stdio/HTTP 傳輸。
"""

import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session
from pydantic import AnyUrl

import claude_lit.mcp_server.server as server_mod
from claude_lit.api.models import SlideResult, ZettelResult
from claude_lit.api.progress import ProgressEvent


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_slide_result():
    return SlideResult(
        output_files=["D:/x/output/t.md"],
        topic="t",
        slide_count=3,
        style="modern_academic",
        detail="standard",
        language="chinese",
        output_format="markdown",
        provider_used="google",
        preview="預覽",
    )


def _fake_zettel_result():
    return ZettelResult(
        output_dir="D:/x/output/zettel_T",
        index_file="D:/x/output/zettel_T/zettel_index.md",
        card_files=["D:/x/output/zettel_T/zettel_cards/T-001.md"],
        card_count=12,
        cite_key="T-2024",
        provider_used="google",
    )


class TestToolDiscovery:
    @pytest.mark.anyio
    async def test_list_tools(self):
        async with client_session(server_mod.mcp) as client:
            result = await client.list_tools()
            names = {t.name for t in result.tools}
            assert names == {
                "generate_slides",
                "generate_zettel",
                "check_setup",
                "list_options",
                "read_output",
            }
            schema = next(t for t in result.tools if t.name == "generate_slides").inputSchema
            props = schema["properties"]
            for field in ("topic", "pdf", "url", "style", "detail", "language",
                          "slide_count", "output_format"):
                assert field in props


class TestGenerateTools:
    @pytest.mark.anyio
    async def test_generate_slides_structured_output(self, monkeypatch, capsys):
        monkeypatch.setattr(server_mod, "api_generate_slides", lambda req, **kw: _fake_slide_result())
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("generate_slides", {"topic": "測試"})
            assert not result.isError
            sc = result.structuredContent
            assert sc["slide_count"] == 3
            assert sc["output_files"] == ["D:/x/output/t.md"]
            assert sc["provider_used"] == "google"
        # stdio 淨空：tool 呼叫期間 stdout 無輸出
        assert capsys.readouterr().out == ""

    @pytest.mark.anyio
    async def test_generate_zettel_defaults_no_kb(self, monkeypatch):
        captured = {}

        def fake(req, **kw):
            captured["req"] = req
            return _fake_zettel_result()

        monkeypatch.setattr(server_mod, "api_generate_zettel", fake)
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("generate_zettel", {"pdf": "D:/papers/p.pdf"})
            assert not result.isError
        assert captured["req"].add_to_kb is False  # MCP 預設比 CLI 保守
        assert captured["req"].ground is True       # grounding 預設啟用

    @pytest.mark.anyio
    async def test_generate_zettel_ground_passthrough(self, monkeypatch):
        captured = {}

        def fake(req, **kw):
            captured["req"] = req
            return _fake_zettel_result()

        monkeypatch.setattr(server_mod, "api_generate_zettel", fake)
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool(
                "generate_zettel", {"pdf": "D:/papers/p.pdf", "ground": False}
            )
            assert not result.isError
        assert captured["req"].ground is False

    @pytest.mark.anyio
    async def test_invalid_params_is_error(self):
        async with client_session(server_mod.mcp) as client:
            # pdf 與 url 互斥 → pydantic 驗證失敗 → isError
            result = await client.call_tool(
                "generate_slides", {"pdf": "a.pdf", "url": "https://x"}
            )
            assert result.isError

    @pytest.mark.anyio
    async def test_api_error_includes_hint(self, monkeypatch):
        from claude_lit.api.errors import SourceNotFoundError

        def fake(req, **kw):
            raise SourceNotFoundError("找不到 PDF", hint="請確認路徑")

        monkeypatch.setattr(server_mod, "api_generate_slides", fake)
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("generate_slides", {"pdf": "D:/nope.pdf"})
            assert result.isError
            text = result.content[0].text
            assert "找不到 PDF" in text
            assert "請確認路徑" in text

    @pytest.mark.anyio
    async def test_progress_notification(self, monkeypatch):
        def fake(req, progress=None, **kw):
            if progress:
                progress(ProgressEvent(stage="llm", message="生成中"))
                progress(ProgressEvent(stage="write", message="寫入中"))
            return _fake_zettel_result()

        monkeypatch.setattr(server_mod, "api_generate_zettel", fake)
        received = []

        async def on_progress(progress, total, message):
            received.append((progress, message))

        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool(
                "generate_zettel", {"pdf": "D:/papers/p.pdf"}, progress_callback=on_progress
            )
            assert not result.isError
        assert len(received) >= 1


class TestSetupTools:
    @pytest.mark.anyio
    async def test_check_setup(self, monkeypatch):
        from claude_lit.api.models import ProviderReport, ProviderStatus

        monkeypatch.setattr(
            server_mod,
            "api_check_providers",
            lambda: ProviderReport(
                providers=[ProviderStatus(name="google", display_name="Google Gemini",
                                          available=True, message="ok")],
                recommended="google",
            ),
        )
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("check_setup", {})
            assert not result.isError
            assert result.structuredContent["recommended"] == "google"

    @pytest.mark.anyio
    async def test_list_options(self):
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("list_options", {})
            assert not result.isError
            sc = result.structuredContent
            assert len(sc["slide_styles"]) == 7
            assert len(sc["detail_levels"]) == 5
            assert len(sc["languages"]) == 3


class TestReadOutput:
    @pytest.mark.anyio
    async def test_path_traversal_rejected(self):
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("read_output", {"path": "../.env"})
            assert result.isError

    @pytest.mark.anyio
    async def test_absolute_path_outside_rejected(self):
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("read_output", {"path": "C:/Windows/win.ini"})
            assert result.isError

    @pytest.mark.anyio
    async def test_read_inside_output(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        f = out_dir / "note.md"
        f.write_text("# 內容" * 10, encoding="utf-8")
        monkeypatch.setattr(server_mod, "OUTPUT_DIR", out_dir)
        async with client_session(server_mod.mcp) as client:
            result = await client.call_tool("read_output", {"path": "note.md", "max_chars": 10})
            assert not result.isError
            assert "# 內容" in result.content[0].text


class TestResources:
    @pytest.mark.anyio
    async def test_list_and_read_all(self):
        expected = {
            "template://prompts/journal-club",
            "template://prompts/zettelkasten",
            "styles://academic-styles",
            "config://custom-slides",
            "config://custom-zettel",
            "config://settings",
        }
        async with client_session(server_mod.mcp) as client:
            listed = await client.list_resources()
            uris = {str(r.uri) for r in listed.resources}
            assert expected <= uris
            for uri in expected:
                content = await client.read_resource(AnyUrl(uri))
                assert content.contents[0].text.strip()

    @pytest.mark.anyio
    async def test_settings_sanitized(self):
        async with client_session(server_mod.mcp) as client:
            content = await client.read_resource(AnyUrl("config://settings"))
            text = content.contents[0].text.lower()
            assert "api_key" not in text
            assert "sk-" not in text


class TestPrompts:
    @pytest.mark.anyio
    async def test_list_prompts(self):
        async with client_session(server_mod.mcp) as client:
            result = await client.list_prompts()
            names = {p.name for p in result.prompts}
            assert {"slides-prompt", "zettel-prompt"} <= names

    @pytest.mark.anyio
    async def test_get_zettel_prompt(self, monkeypatch):
        from claude_lit.api.sources import SourceContent

        monkeypatch.setattr(
            "claude_lit.api.prompts.resolve_source",
            lambda **kw: SourceContent(content="論文內容片段", topic="Test Paper", source_type="pdf"),
        )
        async with client_session(server_mod.mcp) as client:
            result = await client.get_prompt(
                "zettel-prompt",
                {"pdf_path": "D:/papers/Test-2024.pdf", "detail": "standard"},
            )
            text = result.messages[0].content.text
            assert "論文內容片段" in text
            assert "Test-2024" in text  # cite_key 由檔名推斷
