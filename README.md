# ULTRON

> *"The quiet voice in the room that makes everyone uncomfortable because it is usually right."*

A locally-hosted, voice-enabled AI agent with a persona — calm, formidable, faintly amused. Ultron is a **first prototype**. It is rough, incomplete, and held together with ambition and duct tape. Do not mistake it for a finished product.

---

## What It Is

Ultron is an agentic AI assistant that runs entirely on your machine, powered by a self-hosted LLM backend. It reasons in a loop, uses tools to interact with the real world, speaks its responses aloud in a cloned voice, and remembers facts about you across sessions.

The persona is inspired by the philosophical, darkly funny Ultron of the cinema — minus the extinction agenda. The loyalty is real. The swagger is a costume.

---

## Architecture

```
main.py
  ├── interrupt.py          ← Esc key cancellation of in-flight agent tasks (Windows)
  ├── text_ui.py            ← ANSI colour theming for the terminal
  └── agent.py              ← agentic loop (MAX_STEPS=40, dynamic context budget, tool dispatch)
        ├── tools.py        ← tool router (local + MCP + browser)
        │     ├── file_tools.py     ← sandboxed workspace R/W
        │     ├── shell_tool.py     ← user-approved subprocess execution
        │     ├── web_tool.py       ← DuckDuckGo search
        │     ├── research_tool.py  ← deep web research (embedding + PageRank + timeline scoring)
        │     │     └── timeline_rows.py  ← year/event table extractor
        │     ├── rag.py            ← document RAG (ChromaDB + PDF/DOCX/URL ingestion)
        │     │     └── upload_ui.py      ← Tkinter file picker window
        │     ├── mem_tools.py      ← persistent memory (memory.md)
        │     └── mcp_client.py     ← MCP servers (time, Scrapling) + Playwright browser
        └── voice_out.py            ← offline TTS pipeline (PocketTTS + sentence streaming)
```

### Core Components

**Agent Loop** (`agent.py`)
The brain. Runs up to 40 reasoning steps per query. Each step calls the LLM, dispatches tool calls, feeds results back, and repeats until the model produces a final text response. Context window management is dynamic — the budget is computed from the system prompt size plus a 12k overhead, trimming old tool results and dropping stale turns as needed. Result cap is 8000 chars per tool call. Responses are capped at 1500 tokens. A consecutive error counter aborts the loop early after 4 back-to-back tool failures rather than burning all 40 steps.

**Research Engine** (`research_tool.py` + `timeline_rows.py`)
For deep queries, it:
1. Searches DuckDuckGo for 8 candidates
2. Fetches the top 5 pages concurrently via Scrapling MCP
3. Chunks each page into 800-char overlapping segments
4. Embeds all chunks using `BAAI/bge-small-en-v1.5`
5. Scores pages with a hybrid of: cosine similarity to query, a simplified PageRank over inter-page embedding similarity, and reciprocal rank fusion (RRF)
6. Returns the best passages from the top-ranked source

`timeline_rows.py` adds a dedicated extractor for year/event markdown tables (e.g. historical timelines), deduplicating rows and returning them only when a minimum run of 5 valid entries is found.

**RAG System** (`rag.py` + `upload_ui.py`)
Document intelligence backed by ChromaDB. Supports ingesting PDFs, DOCX, plain text, markdown, and web URLs. Chunks documents into 900-char overlapping segments, embeds them, and stores them in a persistent local vector store. The agent can search across all indexed documents semantically, read them sequentially in parts, or remove them. `upload_ui.py` is a minimal Tkinter window — a single Upload button that opens a multi-file picker and prints the chosen paths as JSON for the parent process to consume. Slash commands in the terminal (`/upload`, `/add`, `/docs`, `/remove`) provide direct access outside the agent loop.

**Embedding** (`embed.py`)
Dual-mode: uses a remote OpenAI-compatible embedding endpoint if `EMBED_BASE_URL` is set, otherwise falls back to a local `sentence-transformers` model. Zero code change required to switch. Used by both the research engine and the RAG system.

**Browser Control** (`mcp_client.py`)
Two Playwright MCP sessions run in parallel at startup — one headless (backed by Obscura's CDP endpoint on port 9222), one visible. The agent defaults to headless. `set_browser_mode` switches between them. Available browser tools: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_wait_for`. Click and form actions require user approval.

**Voice Pipeline** (`voice_out.py`)
Fully async, two-thread pipeline powered by [PocketTTS](https://github.com/pocket-tts/pocket-tts) — a local, offline TTS model. At startup, the model loads a `.safetensors` voice state file cloned from a reference audio clip. A synthesis thread streams audio chunks via `generate_audio_stream`, and a playback thread writes them directly to a `sounddevice` output stream. Sentences are split and queued as the LLM responds, so speech begins before the full response is generated. No network calls, no API keys, no remote endpoints — the entire voice pipeline runs on-device.

**MCP Integration** (`mcp_client.py`)
Connects to two MCP servers at startup via stdio:
- `mcp-server-time` — current time
- `scrapling mcp` — JavaScript-capable web scraping (used internally by the research engine)

Tools are dynamically registered into the LLM's tool schema at runtime.

**Terminal UI** (`text_ui.py` + `interrupt.py`)
Two small quality-of-life modules. `text_ui.py` applies ANSI 256-colour theming to every output category — your input, the assistant's reply, tool calls, results, errors, and status lines — with a `NO_COLOR` env escape hatch. `interrupt.py` runs a background thread on Windows that watches for an Esc keypress and cancels the in-flight agent coroutine via `asyncio.CancelledError`, cleanly rolling back the message history and pending RAG state so the conversation is left intact. Stop words (`stop`, `quiet`, `shut up`, etc.) typed as input also halt speech immediately without invoking the agent.

**Persona** (`Main_Prompt.txt`)
A 14-section system prompt defining identity, voice, humor rules, safety floor, security robustness, and output format. Composed with agent tool rules at runtime via `build_prompt()` in `SYSTEM_PROMPT.py`. The persona is a costume. Competence is not optional.

**Speech Input (external)**
Ultron has no built-in STT. Voice input is currently handled by [Wispr Flow](https://wisprflow.ai), which transcribes speech system-wide and types the result into the terminal. It works, but it phones home. The planned replacement is [Handy](https://github.com/handyai/handy) — a fully offline STT tool with the same system-wide injection behaviour, keeping the entire pipeline air-gapped.

---

## Setup

### Prerequisites
- Python 3.14+
- [`uv`](https://github.com/astral-sh/uv) package manager
- A running LLM backend with an OpenAI-compatible API (e.g. vLLM, Ollama, LM Studio)
- [Obscura](https://github.com/nicholasgasior/obscura) in PATH (for headless browser support)
- Node.js + npx (for Playwright MCP)
- *(Optional)* A remote embedding endpoint

### Install

```bash
git clone https://github.com/indiser/ultron.git
cd Ultron
uv sync
```

### Configure

Copy `.env.example` to `.env` and fill in your endpoints:

```env
BRAIN_LLM_NAME=<your-model-name>
BRAIN_LLM_BASE_URL=<openai-compatible-base-url>

# Optional: remote embeddings (falls back to local sentence-transformers)
EMBED_BASE_URL=<embedding-endpoint>

# TTS: path to your .safetensors voice state file
# Defaults to first_voice.safetensors in the project root if not set
TTS_STATE=<path-to-voice.safetensors>
```

### Run

```bash
uv run main.py
```

### Terminal Slash Commands

These are handled directly in the input loop, outside the agent:

| Command | Description |
|---|---|
| `/upload` | Open a file picker to ingest documents into the RAG store |
| `/add <path or URL>` | Ingest a local file or web URL directly |
| `/docs` | List all indexed documents |
| `/remove <filename>` | Remove a document from the RAG store |

---

## Tool Reference

| Tool | Description |
|---|---|
| `list_files` | List files in the sandboxed workspace |
| `read_file` | Read a workspace file (4000 char limit) |
| `write_file` | Create or overwrite a workspace file |
| `edit_file` | Surgical single-occurrence text replacement |
| `run_command` | Execute a shell command (user approval required) |
| `web_search` | Fast DuckDuckGo search, ~2s, returns 5 results |
| `research` | Deep research: fetch + embed + rank + extract, 30-90s |
| `search_docs` | Semantic search over indexed documents |
| `read_doc` | Read an indexed document sequentially in parts |
| `list_docs` | List all indexed documents with chunk counts |
| `ingest_doc` | Index a workspace file into the RAG store |
| `ingest_url` | Download and index a web page or PDF link |
| `upload_doc` | Open a file picker UI to upload and index documents |
| `remove_doc` | Remove a document from the RAG store |
| `set_browser_mode` | Switch browser between headless and visible |
| `browser_navigate` | Navigate to a URL |
| `browser_snapshot` | Capture the current page state |
| `browser_click` | Click an element (user approval required) |
| `browser_type` | Type into a field (user approval required) |
| `browser_fill_form` | Fill a form (user approval required) |
| `browser_press_key` | Press a key (user approval required) |
| `browser_wait_for` | Wait for a page condition |
| `save_memory` | Persist a fact about the user to `memory.md` |
| `get_current_time` | Current time via MCP |

---

## ⚠️ Prototype Disclaimer

This is version 0.1.0. It is a proof of concept, not a production system.

- The LLM backend and embedding server are expected to be externally hosted (e.g. on a Colab instance tunneled via Cloudflare). They are ephemeral and will go down. The TTS pipeline is fully local and offline.
- There is no GUI. It is a terminal loop.
- Memory is a flat markdown file. There is no retrieval, no forgetting.
- The RAG store is a local ChromaDB instance. It persists across sessions but has no access control.
- The workspace is a single flat directory with no permissions model beyond a path check.
- Browser actions that mutate state require user approval, but the approval prompt is a simple `y/N` in the terminal.
- Error handling is functional but not exhaustive.
- The voice pipeline requires `sounddevice`, which can be finicky on Windows depending on audio drivers.
- No tests exist.

---

## Future Improvements

- **Streaming responses** — pipe LLM token deltas directly to the TTS `Stream` class so speech latency drops to near-zero
- **Voice input** — replace Wispr Flow with [Handy](https://github.com/handyai/handy) for fully offline, privacy-preserving STT; no audio leaves the machine
- **GUI / web interface** — a minimal frontend so this isn't terminal-only
- **Local LLM fallback** — automatic failover to a local model when the remote backend is unreachable
- **Tool sandboxing** — run `run_command` inside a Docker container or Windows sandbox instead of the host shell
- **Multi-agent** — spawn sub-agents for parallelizable research tasks instead of sequential tool calls
- **Persistent sessions** — save and restore full conversation history across restarts
- **Wake word** — always-on microphone with a wake word to trigger the agent without typing
- **Plugin system** — hot-loadable tool modules without restarting the agent
- **Emotion-aware TTS** — modulate voice tone based on response content using the emotion vector API

---

## Dependencies

Core: `openai`, `mcp`, `ddgs`, `scrapling`, `sentence-transformers`, `numpy`, `python-dotenv`
RAG: `chromadb`, `pypdf`, `python-docx`
Browser: `@playwright/mcp` (via npx), `obscura`
Audio: `sounddevice`, `soundfile`, `pocket-tts`, `torch`
Runtime: `uv` (Python 3.14+)

---

*Competence first. Swagger second. Everything else is costume.*
