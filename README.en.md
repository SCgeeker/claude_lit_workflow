# Claude Lit Workflow

**Language**: [繁體中文](README.md) ｜ English

![License](https://img.shields.io/badge/license-MIT-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue)

A literature workflow toolkit for note-taking apps — turn a PDF, URL, or topic into academic slides and Zettelkasten atomic cards, output as plain Markdown ready to import into Obsidian and similar tools. Drive it via CLI, an MCP server, or Obsidian QuickAdd.

## Features

- **Slide generation** — 7 academic styles, 5 detail levels, 3 languages; outputs Obsidian Slides / Marp–compatible Markdown or PPTX
- **Atomic card generation** — Zettelkasten cards with cross-paper links and knowledge-base integration
- **Usage guide** — describe what you want in natural language; a chosen LLM replies with the exact CLI command
- **MCP server** — exposes the tools over the Model Context Protocol; any MCP-capable LLM platform can call it (stdio + Streamable HTTP)
- **Multi-provider** — Google Gemini / OpenAI / Anthropic / Ollama / NVIDIA NIM

## Design

```text
PDF / URL / topic
  │
  ├─► uv run slides   →  Markdown slides (Obsidian Slides Extended compatible)
  │        (edit by hand, read deeply)
  │
  └─► uv run zettel   →  output/zettelkasten_notes/{citekey}/
           (optionally --slides-file to reuse your edited slides)
                │
                └──► import into a note app (Obsidian / any Markdown app)
```

Knowledge management (search, links, graphs) is handled by the note app; this tool focuses on **generating high-quality Markdown content**.

## Quick Start

```bash
git clone https://github.com/SCgeeker/claude_lit_workflow.git
cd claude_lit_workflow
uv sync

cp .env.example .env   # Windows: copy .env.example .env; fill in at least one API key
uv run setup           # auto-detect available providers and show suggestions
```

Usage:

```bash
uv run slides --pdf paper.pdf                              # slides from a PDF
uv run slides --url https://arxiv.org/abs/1234 --style teaching
uv run zettel --pdf paper.pdf --detail comprehensive      # atomic cards
uv run zettel --pdf paper.pdf --slides-file output/slides/paper.md   # reuse edited slides
```

## LLM Providers

Put any provider's API key in `.env`:

| Provider | Env var | Recommended model |
|----------|---------|-------------------|
| Google Gemini | `GOOGLE_API_KEY` | gemini-2.5-flash |
| Anthropic Claude | `ANTHROPIC_API_KEY` | claude-haiku-4-5 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini |
| Ollama (local) | `OLLAMA_URL` | llama3.2 |
| NVIDIA NIM | `NVIDIA_API_KEY` | meta/llama-3.1-8b-instruct (default, verified stable) |

`--llm-provider auto` picks an available one. NVIDIA NIM (OpenAI-compatible) is enabled with `--llm-provider nvidia`; it defaults to the verified-stable 8B instruct model. Larger models can be set via `NVIDIA_SLIDES_MODEL` / `NVIDIA_ZETTEL_MODEL` or `--model`.

## CLI Commands

| Command | Purpose |
|---------|---------|
| `uv run setup` | Detect LLM connectivity, show setup suggestions |
| `uv run guide` | Print the tool usage guide (paste into any LLM) |
| `uv run guide "request" --provider X` | Have a chosen LLM reply with the CLI command for your "request" |
| `uv run slides --pdf paper.pdf` | Generate slides from a PDF |
| `uv run zettel --pdf paper.pdf` | Generate atomic cards from a PDF |
| `uv run mcp-server` | Start the MCP server (stdio; `--transport http` for Streamable HTTP) |

Full options: run `uv run <command> --help`, or `uv run guide` to print every option and style; behavior specs live in `openspec/`.

## MCP Server

Any MCP-capable LLM platform (Claude Desktop / Claude Code / Cursor, etc.) can call it:

```bash
uv run mcp-server                                  # stdio (local client)
uv run mcp-server --transport http --port 8765     # Streamable HTTP (remote platforms)

# Register with Claude Code:
claude mcp add lit-workflow -- uv --directory /path/to/claude_lit_workflow run mcp-server
```

Provides 5 tools (generate_slides / generate_zettel / check_setup / list_options / read_output), 6 resources (templates, styles, custom requirements, sanitized settings), and 2 prompts (fully rendered prompts). Generation runs on the server-side LLM; the API key stays in the server process and is never sent over the protocol. Long-running generation emits progress notifications (set client tool timeout ≥ 360s).

## Templates & Config (cwd Override)

The package ships a default set of templates and config (`src/claude_lit/resources/`, bundled in the wheel). At runtime resolution order is: **explicit path > `templates/` and `config/` in the current working directory > package built-in**.

- Working in the repo: edit `templates/` and `config/custom_*.md` directly — changes take effect without reinstalling.
- Installed via wheel elsewhere with no override files: the built-in defaults are used automatically.
- User customization files (`config/custom_slides.md`, `custom_zettel.md`) hold your domain terminology; `--no-custom` skips them, `--custom-file` points to another file.

## Note-App Integration (Obsidian QuickAdd)

Templater user scripts (`*_wrapper.js`) plus `workflow-config.json` let Obsidian QuickAdd trigger generation directly:

- **Program_verse** — full pipeline: slides + zettel + import + guide
- **Ideaverse_Growing** — slides only, output to the vault's `+/`

Each wrapper reads the config, collects parameters via suggesters, and calls this tool with `exec("uv run …")`, setting `PYTHONIOENCODING=utf-8` so Chinese output is not garbled.

## Citekey (Output Filenames)

Output filenames use `Author-Year` (e.g. `Barsalou-1999`). If you use Zotero or another reference manager, pass `--citekey` to set your own key directly:

```bash
uv run zettel --pdf paper.pdf --citekey Barsalou-1999
```

Without it, the key is resolved automatically from DOI / CrossRef.

## Output Layout

```text
output/
├── slides/
│   └── {citekey}_{date}.md
└── zettelkasten_notes/
    └── zettel_{citekey}_{date}_{model}/
        ├── zettel_index.md
        └── zettel_cards/{citekey}-NNN.md
```

## Tech Stack

Python 3.10+ / uv ｜ pydantic ｜ Jinja2 (prompt templates) ｜ FastMCP (MCP server) ｜ LLMs: Gemini / OpenAI / Anthropic / Ollama / NVIDIA NIM

Specs and change history live in `openspec/` (spec-driven development; specs are the source of truth for behavior).

## License

MIT License — see [LICENSE](LICENSE). Copyright (c) 2025-2026 Sau-Chin Chen.

---

**Version**: 0.12.0 ｜ **Updated**: 2026-07-09
