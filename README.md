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
  └── agent.py          ← agentic loop (MAX_STEPS=20, context trimming, tool dispatch)
        ├── tools.py    ← tool router (local + MCP)
        │     ├── file_tools.py     ← sandboxed workspace R/W
        │     ├── shell_tool.py     ← user-approved subprocess execution
        │     ├── web_tool.py       ← DuckDuckGo search
        │     ├── research_tool.py  ← deep web research (embedding + PageRank scoring)
        │     ├── mem_tools.py      ← persistent memory (memory.md)
        │     └── mcp_client.py     ← MCP servers (time, web scraping via Scrapling)
        └── voice_out.py            ← async TTS pipeline (sentence streaming + caching)
```

### Core Components

**Agent Loop** (`agent.py`)
The brain. Runs up to 20 reasoning steps per query. Each step calls the LLM, dispatches tool calls, feeds results back, and repeats until the model produces a final text response. Includes context window management via trimming old tool results and dropping stale conversation turns.

**Research Engine** (`research_tool.py`)
The most technically interesting piece. For deep queries, it:
1. Searches DuckDuckGo for 8 candidates
2. Fetches the top 5 pages concurrently via Scrapling MCP
3. Chunks each page into 800-char overlapping segments
4. Embeds all chunks using `BAAI/bge-small-en-v1.5`
5. Scores pages with a hybrid of: cosine similarity to query, a simplified PageRank over inter-page embedding similarity, and reciprocal rank fusion (RRF)
6. Returns the best passages from the top-ranked source

**Embedding** (`embed.py`)
Dual-mode: uses a remote OpenAI-compatible embedding endpoint if `EMBED_BASE_URL` is set, otherwise falls back to a local `sentence-transformers` model. Zero code change required to switch.

**Voice Pipeline** (`voice_out.py`)
Fully async, two-thread pipeline powered by [PocketTTS](https://github.com/pocket-tts/pocket-tts) — a local, offline TTS model. At startup, the model loads a `.safetensors` voice state file cloned from a reference audio clip. A synthesis thread streams audio chunks via `generate_audio_stream`, and a playback thread writes them directly to a `sounddevice` output stream. Sentences are split and queued as the LLM responds, so speech begins before the full response is generated. No network calls, no API keys, no remote endpoints — the entire voice pipeline runs on-device.

**MCP Integration** (`mcp_client.py`)
Connects to two MCP servers at startup via stdio:
- `mcp-server-time` — current time
- `scrapling mcp` — JavaScript-capable web scraping

Tools are dynamically registered into the LLM's tool schema at runtime.

**Persona** (`Main_Prompt.txt`)
A 14-section system prompt defining identity, voice, humor rules, safety floor, security robustness, and output format. The persona is a costume. Competence is not optional.

**Speech Input (external)**
Ultron has no built-in STT. Voice input is currently handled by [Wispr Flow](https://wisprflow.ai), which transcribes speech system-wide and types the result into the terminal. It works, but it phones home. The planned replacement is [Handy](https://github.com/cjpais/handy) — a fully offline STT tool with the same system-wide injection behaviour, keeping the entire pipeline air-gapped.

---

## Setup

### Prerequisites
- Python 3.14+
- [`uv`](https://github.com/astral-sh/uv) package manager
- A running LLM backend with an OpenAI-compatible API (e.g. vLLM, Ollama, LM Studio)
- *(Optional)* A remote embedding endpoint
### Install

```bash
git clone https://github.com/indiser/ultron
cd ultron
uv sync
```

### Configure

Copy `.env.example` to `.env` and fill in your endpoints:

```env
BRAIN_LLM_NAME=<your-model-name>
BRAIN_LLM_BASE_URL=<openai-compatible-base-url>

# Optional: remote embeddings (falls back to local sentence-transformers)
EMBED_BASE_URL=<embedding-endpoint>

# TTS: path to your voice state file (generated from a reference audio clip)
TTS_STATE=<path-to-voice.safetensors>
```

### Run

```bash
uv run main.py
```

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
| `save_memory` | Persist a fact about the user to `memory.md` |
| `get_current_time` | Current time via MCP |

---

## ⚠️ Prototype Disclaimer

This is version 0.1.0. It is a proof of concept, not a production system.

- The LLM backend and embedding server are expected to be externally hosted (e.g. on a Colab instance tunneled via Cloudflare). They are ephemeral and will go down. The TTS pipeline is fully local and offline.
- There is no GUI. It is a terminal loop.
- Memory is a flat markdown file. There is no vector store, no retrieval, no forgetting.
- The workspace is a single flat directory with no permissions model beyond a path check.
- Error handling is functional but not exhaustive.
- The voice pipeline requires `sounddevice`, which can be finicky on Windows depending on audio drivers.
- No tests exist.

---

## Future Improvements

- **Streaming responses** — pipe LLM token deltas directly to the TTS `Stream` class so speech latency drops to near-zero
- **Vector memory** — replace `memory.md` with a proper embedding store (FAISS or ChromaDB) for semantic retrieval over long-term memory
- **GUI / web interface** — a minimal frontend so this isn't terminal-only
- **Local LLM fallback** — automatic failover to a local model when the remote backend is unreachable
- **Tool sandboxing** — run `run_command` inside a Docker container or Windows sandbox instead of the host shell
- **Multi-agent** — spawn sub-agents for parallelizable research tasks instead of sequential tool calls
- **Persistent sessions** — save and restore full conversation history across restarts
- **Wake word** — always-on microphone with a wake word to trigger the agent without typing
- **Voice input** — replace Wispr Flow with [Handy](https://github.com/cjpais/handy) for fully offline, privacy-preserving STT; no audio leaves the machine
- **Plugin system** — hot-loadable tool modules without restarting the agent
- **Emotion-aware TTS** — use the emotion vector API (already partially explored in `voice.py`) to modulate tone based on response content

---

## Dependencies

Core: `openai`, `mcp`, `ddgs`, `scrapling`, `sentence-transformers`, `numpy`, `python-dotenv`
Audio: `sounddevice`, `pocket-tts`, `torch`
Runtime: `uv` (Python 3.14+)

---

*Competence first. Swagger second. Everything else is costume.*
