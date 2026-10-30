# Claude Lit Workflow

**Language**: [繁體中文](README.md) ｜ English

![License](https://img.shields.io/badge/license-MIT-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue)

A literature workflow toolkit for note-taking apps — turn a PDF, URL, or topic into academic slides and Zettelkasten atomic cards, output as plain Markdown ready to import into Obsidian and similar tools. Drive it via CLI, an MCP server, or Obsidian QuickAdd.

## Features

- **Slide generation** — 7 academic styles, 5 detail levels, 3 languages; outputs Obsidian Slides / Marp–compatible Markdown or PPTX
- **Atomic card generation** — Zettelkasten cards with cross-paper links and knowledge-base integration
- **Web service** — deploy to a cloud server; upload articles, pick templates and type prompts from any browser (`uv run web`, see `deploy/`)
- **Multiple media** — beyond research papers: lecture / podcast transcripts (.srt / .vtt / .txt), blog posts, textbooks and monographs (`--media`)
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
| `uv run zettel --text ep42.srt --media podcast` | Cards from a podcast transcript (views attributed to speakers; sidecar carries timestamps) |
| `uv run slides --pdf book.pdf --media textbook --chapter 3` | Process a textbook / monograph one chapter at a time |
| `uv run mcp-server` | Start the MCP server (stdio; `--transport http` for Streamable HTTP) |
| `uv run web` | Start the web service (needs `uv sync --extra web`; see `deploy/README.md` for public deployment) |

### Media types (`--media`)

| Media | What changes | Sources |
|-------|-------------|---------|
| `paper` (default) | Research papers — behavior unchanged | `--pdf` / `--url` |
| `lecture` | Talk transcripts: follow the talk's progression, keep spoken wording in quotes | `--text` (.srt / .vtt / .txt) |
| `podcast` | Multi-speaker conversations: every view attributed to a speaker, disagreements become contrast cards | `--text` |
| `blog` | Blog posts: separate claims / evidence / rhetoric, note datedness | `--url` / `--text` |
| `textbook` | Textbooks: objectives → concepts → worked examples → self-test | `--pdf` / `--text` (incl. .epub) + `--chapter` |
| `monograph` | Scholarly books: argument map, author's claims vs. views the author reports | same |

- `--meta KEY=VALUE` (repeatable) supplies source info for the title slide and card source links, e.g. `--meta speaker="Jane Doe" --meta year=2025`
- `--chapter 3` / `3-5` processes only those chapters; the cite_key gets a `-ch03` suffix so chapters of one book never collide
- Transcripts are cleaned automatically: subtitle indices and timecodes removed, fillers dropped (`--keep-fillers` keeps them), same-speaker turns merged, `[hh:mm:ss]` markers inserted
- Media behavior lives in `templates/styles/media_profiles.yaml` and can be edited directly (the cwd override applies)

Full options: run `uv run <command> --help`, or `uv run guide` to print every option and style; behavior specs live in `openspec/`.

## MCP Server

Any MCP-capable LLM platform (Claude Desktop / Claude Code / Cursor, etc.) can call it:

```bash
uv run mcp-server                                  # stdio (local client)
uv run mcp-server --transport http --port 8765     # Streamable HTTP (remote platforms)

# Register with Claude Code:
claude mcp add lit-workflow -- uv --directory /path/to/claude_lit_workflow run mcp-server
```

Provides 5 tools (generate_slides / generate_zettel / check_setup / list_options / read_output), 7 resources (templates, styles, media types, custom requirements, sanitized settings), and 2 prompts (fully rendered prompts). In HTTP mode, setting `WEB_API_TOKEN` requires a bearer token; remote clients that cannot pass server paths can send the source text to `generate_zettel` via `content` (with a `cite_key`). Generation runs on the server-side LLM; the API key stays in the server process and is never sent over the protocol. Long-running generation emits progress notifications (set client tool timeout ≥ 360s).

## Web Service (Cloud Deployment)

```bash
uv sync --extra web
uv run web                                   # local http://127.0.0.1:8000
cd deploy && docker compose up -d --build    # VPS: Docker + Caddy with automatic HTTPS
```

- Web UI: upload a PDF / EPUB / transcript or paste a URL → choose outputs, media type and style → type a prompt (appended to the template; it cannot change the output format) or describe what you want in one sentence and let an LLM suggest settings → live progress → preview and download a zip (same layout as the local `output/`)
- The same deployment also serves a REST API, `/mcp` (sharing `WEB_API_TOKEN` with the web UI) and an Obsidian QuickAdd remote mode (`examples/quickadd/lit_remote.js`, no local uv needed)
- Safety: refuses to start on a public address without auth; API keys stay on the server; upload types and sizes are restricted; job data, including the uploaded originals, is deleted after the retention period (default 7 days)

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

**Version**: 0.12.0 ｜ **Updated**: 2026-08-02
