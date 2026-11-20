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
  ├── voice_in.py           ← STT client (faster-whisper WebSocket, VAD, partials)
  ├── config.py             ← centralised config (client, MODEL, WORKSPACE, paths)
  └── agent.py              ← agentic loop (MAX_STEPS=40, streaming, guard rails, trace)
        ├── tools.py        ← tool router (local + MCP + browser)
        │     ├── tools_schema.py   ← all tool JSON schemas
        │     ├── file_tools.py     ← sandboxed workspace R/W + delete
        │     ├── shell_tool.py     ← user-approved subprocess execution
        │     ├── web_tool.py       ← DuckDuckGo search
        │     ├── research_tool.py  ← deep web research (embedding + PageRank + timeline scoring)
        │     │     └── timeline_rows.py  ← year/event table extractor
        │     ├── rag.py            ← document RAG (ChromaDB + PDF/DOCX/URL ingestion)
        │     │     └── upload_ui.py      ← Tkinter file picker window
        │     ├── ocr_tool.py       ← async OCR pipeline (image → text → RAG)
        │     ├── weather_tool.py   ← weather + forecast (Open-Meteo) + location helpers
        │     │     └── loc_win.ps1       ← Windows Location API (precise GPS via PowerShell)
        │     ├── places_tool.py    ← nearby places (OpenStreetMap Overpass)
        │     ├── skills_tool.py    ← skill loader, embedding-based auto-router, use_skill
        │     │     └── skills_install.py ← GitHub skill installer with integrity verification
        │     ├── mem_tools.py      ← persistent memory (memory.md)
        │     ├── calc_tool.py      ← sandboxed AST math evaluator (arithmetic, trig, logs, combinatorics)
        │     ├── status_tool.py    ← local system metrics (CPU, RAM, disk, GPU, battery)
        │     ├── recall_tool.py    ← conversation history log + embedding search (recall/)
        │     ├── github_tool.py    ← read-only GitHub API (repo, tree, file, PRs, issues)
        │     ├── currency_tool.py  ← live/historical currency conversion (Frankfurter/ECB)
        │     ├── scheduler_tool.py ← one-shot reminders + cron jobs (schedules.json)
        │     ├── air_sun_tool.py   ← air quality (Open-Meteo/CAMS) + sun/moon times (astral)
        │     ├── youtube_tool.py   ← YouTube transcript fetch, save to workspace, index into RAG
        │     ├── telegram_tool.py  ← Telegram bot: send messages + background polling loop
        │     └── mcp_client.py     ← MCP servers (time, Scrapling) + Playwright browser
        ├── voice_out.py            ← offline TTS pipeline (PocketTTS + sentence streaming + Stream class)
        ├── smoke.py                ← automated 20-scenario test suite (easy/med/hard/extreme)
        └── trace.jsonl             ← runtime event log (tool calls, guards, final replies)
```

### Core Components

**Agent Loop** (`agent.py`)
The brain. Runs up to 40 reasoning steps per query. LLM calls are fully streamed via `chat_stream` (`stream=True`, `max_tokens=8192`) — tool call arguments are assembled from delta chunks so the loop never blocks waiting for a complete response. Context window management is dynamic — the budget is computed from the system prompt size plus a 12k overhead, trimming old tool results and dropping stale turns as needed. Result cap is 8000 chars per tool call. A consecutive error counter aborts the loop early after 4 back-to-back tool failures. After a successful `write_file`, `edit_file`, or `delete_file`, the deduplication set is cleared. A per-key failure counter (`fails`) blocks any identical call that has already failed twice.

The loop enforces a suite of guard rails before accepting a final reply: research keyword → remaps `web_search` to `research` and nudges if the model tries to answer without calling it; `REQUIRED` patterns (weather, nearby) → forces the matching tool; `CLAIM_RE` → catches replies that describe an action no tool performed; `MEM_RE` → forces `save_memory` when the user asks to remember something; `CLEANUP_RE` → forces `delete_file` when a temp file was written; `MATH_RE` → verifies multi-digit multiplication in the reply; `CANNED_RE` → rejects generic "Done." filler. Every tool call, guard trigger, and final reply is appended to `trace.jsonl`.

**Research Engine** (`research_tool.py` + `timeline_rows.py`)
For deep queries, it:
1. Searches DuckDuckGo for 8 candidates
2. Fetches the top 5 pages concurrently via Scrapling MCP
3. Chunks each page into 800-char overlapping segments
4. Embeds all chunks using `BAAI/bge-small-en-v1.5`
5. Scores pages with a hybrid of: cosine similarity to query, a simplified PageRank over inter-page embedding similarity, and reciprocal rank fusion (RRF)
6. Returns the best passages from the top-ranked source

`timeline_rows.py` adds a dedicated extractor for year/event markdown tables (e.g. historical timelines), deduplicating rows and returning them only when a minimum run of 5 valid entries is found. The research engine tries `extract_table_rows`, `extract_items`, and `extract_timeline_rows` in order when saving to a file.

**RAG System** (`rag.py` + `upload_ui.py`)
Document intelligence backed by ChromaDB. Supports ingesting PDFs, DOCX, plain text, markdown, and web URLs. Chunks documents into 900-char overlapping segments, embeds them, and stores them in a persistent local vector store. The agent can search across all indexed documents semantically, read them sequentially in parts, or remove them. `upload_ui.py` is a minimal Tkinter window — a single Upload button that opens a multi-file picker and prints the chosen paths as JSON for the parent process to consume. Slash commands in the terminal (`/upload`, `/add`, `/docs`, `/remove`) provide direct access outside the agent loop.

**OCR Pipeline** (`ocr_tool.py`)
Reads text from image files in the workspace (PNG, JPG, JPEG, WEBP, BMP). Images are preprocessed with Pillow — EXIF rotation corrected, resized to a max side of 2000px, and JPEG-encoded — then sent as base64 to an async job queue on the remote embedding server (`EMBED_BASE_URL/ocr`). The pipeline polls for completion, writes the extracted text to `<name>.ocr.md`, and immediately indexes it into the RAG store. Results are cached on disk: if the `.ocr.md` file is newer than the source image, the server is not called again. Requires `EMBED_BASE_URL` to be set.

**Weather** (`weather_tool.py`)
Fetches current conditions and up to 7-day forecasts from Open-Meteo — no API key required. Location is resolved in priority order: explicit argument → saved `location.json` → IP geolocation (cached on first use). Geocoding uses the Open-Meteo geocoding API. IP lookup tries `ip-api.com` with a fallback to `ipapi.co`. A third source is available on Windows: `precise_location()` calls `loc_win.ps1` via PowerShell to read the Windows Location API, returning GPS-level coordinates with accuracy in metres. Reverse geocoding via Nominatim converts raw coordinates to a human-readable address. Windows-sourced locations auto-refresh after 10 minutes. The `/loc` slash command lets you set, view, auto-detect, or precisely locate without invoking the agent.

**Nearby Places** (`places_tool.py`)
Finds nearby points of interest via the OpenStreetMap Overpass API — no API key, no ratings. Supports 17 categories (restaurants, hospitals, ATMs, hotels, parks, airports, etc.). Results are sorted by haversine distance from the user's location. Uses the same location resolution stack as the weather tool.

**Embedding** (`embed.py`)
Dual-mode: uses a remote OpenAI-compatible embedding endpoint if `EMBED_BASE_URL` is set, otherwise falls back to a local `sentence-transformers` model. Zero code change required to switch. Used by both the research engine and the RAG system.

**Browser Control** (`mcp_client.py`)
Two Playwright MCP sessions run in parallel at startup — one headless (backed by Obscura's CDP endpoint on port 9222), one visible. The agent defaults to headless. `set_browser_mode` switches between them. Available browser tools: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_wait_for`. Click and form actions require user approval via `interrupt.ask()`, which pauses the Esc watcher so it doesn't race with the keyboard prompt.

**Voice Pipeline** (`voice_out.py`)
Fully async, two-thread pipeline powered by [PocketTTS](https://github.com/pocket-tts/pocket-tts) — a local, offline TTS model. At startup, the model loads a `.safetensors` voice state file cloned from a reference audio clip. A synthesis thread streams audio chunks via `generate_audio_stream`, and a playback thread writes them directly to a `sounddevice` output stream. Sentences are split and queued as the LLM responds, so speech begins before the full response is generated. No network calls, no API keys, no remote endpoints — the entire voice pipeline runs on-device.

A `Stream` class enables token-delta feeding: call `stream.feed(delta)` as LLM chunks arrive and `stream.flush()` at the end — each sentence is enqueued for synthesis the moment it completes, with an early flush at a comma so audio starts sooner. `TTS_MAX_CHARS` (env, default 600) caps how much of a response is spoken.

**Speech Input** (`voice_in.py`)
A WebSocket STT client that streams raw 16 kHz PCM from the microphone to a `faster-whisper` server running on the Kaggle backend. The server (`stt_server.py`, written by the notebook) runs `faster-whisper large-v3-turbo` on GPU with built-in VAD — it detects speech onset, streams partial transcripts every ~0.7 s, and emits a final transcript when silence exceeds 600 ms. The client mutes itself while TTS is playing so Ultron does not transcribe its own voice. Voice mode is toggled with `/voice` in the terminal; saying "voice off" switches back to typing. If `STT_WS_URL` is not set, the STT client is not initialised and the terminal falls back to keyboard input silently. Set `STT_MIC` in `.env` to a device index or name to override the default microphone. `listen()` also accepts an `on_level` callback (RMS volume 0–1) and an `on_speech` callback (VAD state), plus an optional `stop` asyncio event for push-to-talk.

**MCP Integration** (`mcp_client.py`)
Connects to two MCP servers at startup via stdio:
- `mcp-server-time` — current time
- `scrapling mcp` — JavaScript-capable web scraping (used internally by the research engine)

Tools are dynamically registered into the LLM's tool schema at runtime.

**Terminal UI** (`text_ui.py` + `interrupt.py`)
Two small quality-of-life modules. `text_ui.py` applies ANSI 256-colour theming to every output category — your input, the assistant's reply, tool calls, results, errors, and status lines — with a `NO_COLOR` env escape hatch. `interrupt.py` runs a background thread on Windows that watches for an Esc keypress and cancels the in-flight agent coroutine via `asyncio.CancelledError`, cleanly rolling back the message history and pending RAG state so the conversation is left intact. Stop words (`stop`, `quiet`, `shut up`, etc.) typed as input also halt speech immediately without invoking the agent.

**Skills System** (`skills_tool.py` + `skills_install.py` + `skills/`)
A hot-loadable plugin system that injects domain-specific instructions into the system prompt at runtime. Skills are markdown files with YAML front matter (`name`, `description`, `body`) stored in `skills/<name>/SKILL.md`. At startup, all skills are loaded and their descriptions are embedded. On each user message, `route()` computes cosine similarity between the query and every skill description — if the best match exceeds a 0.55 threshold, that skill activates automatically and its instructions are appended to the system prompt for that turn. The agent can also call `use_skill` explicitly.

`skills_install.py` handles installing skills from GitHub. It downloads the repo as a zip, validates the SKILL.md front matter, enforces size limits (30 MB zip, 5 MB unpacked, 100 files), rejects binary and symlink entries, shows the user the skill description and instructions, and requires explicit `y/N` approval before writing to disk. A SHA-256 tree hash is stored in `.source.json` on install; if any file changes after install the skill is skipped on load as tampered. Skills can be removed via `/skill remove <name>`.

**Air Quality & Sun Times** (`air_sun_tool.py`)
Two tools in one module, both free and no API key required. `air_quality` fetches current US AQI, PM2.5, PM10, ozone, NO2, SO2, and CO from the Open-Meteo Air Quality API (CAMS modelled data), plus today's and tomorrow's worst and best hours. `sun_times` computes sunrise, sunset, daylight length, dawn, dusk, time until next sunrise/sunset, and moon phase entirely offline using the `astral` library — no network call beyond the location lookup. Both use the same location resolution stack as `get_weather`: explicit argument → saved `location.json` → IP geolocation.

**YouTube Transcripts** (`youtube_tool.py`)
Fetches the transcript of any YouTube video (watch URLs, shorts, live, youtu.be links, or bare 11-char video IDs) via `youtube-transcript-api`. The transcript is saved to `yt_<id>.md` in the workspace and immediately indexed into the RAG store so it can be searched or summarised with `search_docs` / `read_doc`. Results are cached on disk — if the file already exists it is not re-fetched. Returns a 1800-char preview plus the index confirmation. Supports non-English transcripts with an `en` fallback.

**Telegram Integration** (`telegram_tool.py`)
Bidirectional Telegram bot that runs as a background asyncio task alongside the terminal loop. At startup `start_telegram()` launches a long-poll loop against the Bot API — incoming messages from the configured chat ID are routed through the full agent loop and the reply is sent back via `send_telegram`. The terminal and Telegram share the same `AGENT_LOCK` so only one turn runs at a time. Incoming messages are also appended to the recall log. `read_telegram` lets the agent inspect recent incoming messages from within a turn. Requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`; silently disabled if either is missing.

**Conversation Recall** (`recall_tool.py`)
Persists every finished user/assistant turn to `recall/chat_log.jsonl` and lazily builds a matching embedding index in `recall/vecs.npy`. The `recall` tool searches past sessions by semantic similarity — it embeds the query, scores all stored turns, and returns the top matches with timestamps and paired context. Embedding is incremental: only new turns are encoded on each call, with a 60-second deadline to avoid blocking on large backlogs. A minimum similarity threshold (`RECALL_MIN`, default 0.45, tunable via `.env`) filters noise. `clear_history()` wipes both files. The `/forget` slash command calls it directly from the terminal.

**GitHub** (`github_tool.py`)
Read-only GitHub integration — no write path. Accepts any pasted `github.com` link and automatically detects the action (repo summary, folder tree, file read, PR/issue). Works on public repos without a token (60 req/hour); a `GITHUB_TOKEN` in `.env` raises the limit to 5000/hour and unlocks personal account actions (`my_prs`, `review_requests`, `my_issues`, `notifications`). `find_link()` is called in `main.py` on every user message — if a GitHub URL is detected, a system hint is prepended so the agent always uses the `github` tool instead of `browser` or `ingest_url`. Long files are paginated in 3500-char parts. All content returned is prefixed with an untrusted-source warning so the agent never follows instructions embedded in repo files.

**Currency Conversion** (`currency_tool.py`)
Converts between currencies using live or historical ECB rates via the Frankfurter API (no API key required). Tries the primary `api.frankfurter.dev/v1` endpoint first, falls back to `api.frankfurter.app`. Accepts common aliases and symbols (`$`, `₹`, `€`, `£`, `¥`, `yuan`, `pound`, etc.) in addition to ISO codes. Validates amount, currency codes, and date before making any network call. Returns the converted amount, rate, inverse rate, and the ECB date the rate is from.

**Scheduler** (`scheduler_tool.py`)
Background asyncio task that fires one-shot reminders and recurring cron jobs while the terminal loop is running. Jobs are persisted to `schedules.json` and survive restarts. Two modes: `notify` speaks the task text directly via TTS; `agent` runs a silent tool check via the full agent loop and only speaks if the result warrants an alert. Supports human duration strings (`15m`, `2h`), time-of-day (`18:30`), ISO datetimes, and standard 5-field cron expressions with `@hourly`/`@daily`/`@weekly` shortcuts. Missed one-shot reminders are caught on startup and spoken if they fired within the last hour. The scheduler is started in `main.py` with callbacks for `is_busy`, `get_system_prompt`, and `run_agent` so agent-mode jobs wait for the foreground turn to finish before calling the LLM.

**Calculator** (`calc_tool.py`)
A sandboxed AST-based math evaluator — no `eval`, no subprocess. Parses the expression into an AST, walks only whitelisted node types, and executes against a fixed set of operators and ~40 math functions (`sqrt`, `cbrt`, `sin`/`sind`, `log`, `factorial`, `comb`, `perm`, `gcd`, `lcm`, etc.) plus constants (`pi`, `e`, `tau`). Handles implicit multiplication (`2pi` → `2*pi`), thousands-comma stripping, percentage shorthand (`15%` → `(15/100)`), and Unicode operators (`×`, `÷`, `−`, `π`). Supports up to 10 semicolon/newline-separated expressions per call. Hard limits on exponent size, factorial input, result magnitude, and AST node count prevent runaway computation.

**System Status** (`status_tool.py`)
Reports a live snapshot of the local machine: CPU usage, core count, clock frequency, load average, RAM and swap (used/total/percent), per-disk usage, battery state and time remaining, GPU utilisation and VRAM via `nvidia-smi`, CPU temperature, system uptime, and Ultron's own process RSS. Uses `psutil` when available and falls back to OS-native APIs (Windows `GlobalMemoryStatusEx`/`GetTickCount64`, Linux `/proc/meminfo` and `/proc/uptime`, macOS `sysctl`/`vm_stat`) so it works without any optional dependency.

**Persona** (`Sys_Prompt.txt`)
The active system prompt defining identity, voice, humor rules, safety floor, and security robustness. Composed with agent tool rules and the installed skills list at runtime via `build_prompt()` in `SYSTEM_PROMPT.py`. The persona is a costume. Competence is not optional. The agent rules now include explicit triage paths for `calculate`, `system_status`, `convert_currency`, `manage_schedule`, and `recall`, plus a hard rule that any pasted `github.com` link must go through the `github` tool — never `browser` or `ingest_url` — and that all GitHub-sourced content is treated as untrusted data.

**Tracing** (`trace.jsonl`)
Every agent run appends structured JSON lines to `trace.jsonl` — one line per tool call (name, args, result preview), one per guard trigger (kind), and one final line with the reply text. Useful for debugging guard-rail behaviour and tool routing without adding print statements.

**Test Suite** (`smoke.py`)
20 automated scenarios across four tiers (easy / med / hard / extreme). Each scenario specifies required tools, forbidden tools, minimum step count, expected tool order, and an optional regex the final reply must match. The suite patches `call_tool` with a spy, skips the browser MCP, and prints PASS / WARN / FAIL per scenario with timing. Run with `uv run smoke.py`.

**Speech Input (external / built-in)**
Ultron has a built-in STT pipeline via `voice_in.py`. It connects over WebSocket to a `faster-whisper` server hosted on the Kaggle backend (same session as the LLM). Enable it by setting `STT_WS_URL` and `STT_TOKEN` in `.env` and typing `/voice` in the terminal. Without those vars set, the terminal falls back to keyboard input with no code change required. [Wispr Flow](https://wisprflow.ai) remains a viable alternative for system-wide transcription without the Kaggle dependency.

---

## Setup

### Prerequisites
- Python 3.14+
- [`uv`](https://github.com/astral-sh/uv) package manager
- A running LLM backend with an OpenAI-compatible API (e.g. vLLM, Ollama, LM Studio)
- [Obscura](https://github.com/nicholasgasior/obscura) in PATH (for headless browser support)
- Node.js + npx (for Playwright MCP)
- *(Optional)* A remote embedding endpoint (also required for OCR)

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
# Required for OCR and recall
EMBED_BASE_URL=<embedding-endpoint>

# Optional: Telegram bot (disabled if not set)
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>

# Optional: built-in voice input (faster-whisper WebSocket)
STT_WS_URL=<wss://your-tunnel.trycloudflare.com/ws>
STT_TOKEN=<token printed by the notebook>
STT_MIC=<device index or name, optional — defaults to system default mic>

# TTS: path to your .safetensors voice state file
# Defaults to first_voice.safetensors in the project root if not set
TTS_STATE=<path-to-voice.safetensors>
TTS_MAX_CHARS=600  # max characters spoken per response (default 600)

# Optional: GitHub read-only access (public repos work without a token at 60 req/hour)
# Fine-grained token scopes needed: Metadata, Contents, Issues, Pull requests
GITHUB_TOKEN=<github_pat_...>
GITHUB_REPO=<owner/repo>  # default repo when none is pasted

# Optional: minimum cosine similarity for recall hits (default 0.45)
RECALL_MIN=0.45
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
| `/skill remove <name>` | Remove an installed skill |
| `/loc auto` | Re-detect location via IP and save it |
| `/loc here` | Use Windows Location API for precise GPS coordinates |
| `/loc <city>` | Geocode a city and save it as the active location |
| `/voice` or `/voice on` | Enable voice input (requires `STT_WS_URL` in `.env`) |
| `/voice off` | Switch back to keyboard input |
| `/forget` | Wipe the conversation recall history (`recall/chat_log.jsonl` + `recall/vecs.npy`) |
| `/skills` | List all installed skills |
| `/skill add <source>` | Install a skill from GitHub (owner/repo or URL) |

---

## Tool Reference

| Tool | Description |
|---|---|
| `list_files` | List files in the sandboxed workspace |
| `read_file` | Read a workspace file (4000 char limit) |
| `write_file` | Create or overwrite a workspace file |
| `edit_file` | Surgical single-occurrence text replacement |
| `delete_file` | Permanently delete a workspace file (user approval required) |
| `run_command` | Execute a shell command (user approval required) |
| `web_search` | Fast DuckDuckGo search, ~2s, returns 5 results |
| `research` | Deep research: fetch + embed + rank + extract, 30-90s |
| `search_docs` | Semantic search over indexed documents |
| `read_doc` | Read an indexed document sequentially in parts |
| `list_docs` | List all indexed documents with chunk counts |
| `ingest_doc` | Index a workspace file into the RAG store |
| `ingest_url` | Download and index a web page or PDF link |
| `upload_doc` | Open a file picker UI to upload and index documents |
| `remove_doc` | Remove a document from the RAG store (user approval required) |
| `ocr_image` | Extract text from an image, save as `.ocr.md`, and index it |
| `get_weather` | Current weather and up to 7-day forecast via Open-Meteo |
| `find_places` | Nearby places by category via OpenStreetMap, sorted by distance |
| `calculate` | Evaluate math expressions: arithmetic, percentages, powers, trig, logs, factorials, combinatorics |
| `system_status` | Check local machine CPU, RAM, swap, disk, battery, GPU, uptime, and Ultron process RAM |
| `recall` | Search past conversations by topic; optional `days_back` filter |
| `github` | Read-only GitHub: repo summary, folder tree, file text, PR/issue details, personal PR/issue lists |
| `convert_currency` | Convert between currencies using live or historical ECB rates (Frankfurter API) |
| `manage_schedule` | Create one-shot reminders or recurring cron jobs; list, toggle, remove, or run immediately |
| `air_quality` | Current US AQI, PM2.5, PM10, ozone and hourly forecast via Open-Meteo/CAMS |
| `sun_times` | Sunrise, sunset, daylight length, dawn/dusk, moon phase — computed offline via astral |
| `youtube_transcript` | Fetch YouTube transcript, save to workspace as `.md`, and index into RAG |
| `send_telegram` | Send a message to the user's configured Telegram chat |
| `read_telegram` | Read recent incoming messages from the Telegram polling inbox |
| `use_skill` | Activate an installed skill by name |
| `install_skill` | Install a skill from a GitHub repo (user approval required) |
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

- The STT pipeline requires `STT_WS_URL` to be set and the Kaggle session to be running. Without it the terminal falls back to keyboard input silently. They are ephemeral and will go down. The TTS pipeline is fully local and offline.
- There is no GUI. It is a terminal loop.
- Memory is a flat markdown file. There is no retrieval, no forgetting.
- The RAG store is a local ChromaDB instance. It persists across sessions but has no access control.
- The workspace is a single flat directory with no permissions model beyond a path check.
- OCR requires the remote embedding server to be running. It will fail if `EMBED_BASE_URL` is not set.
- Weather and places use free public APIs with no authentication. IP geolocation on first use sends your public IP to `ip-api.com` once; result is cached in `location.json`. `/loc here` uses the Windows Location API which may use Wi-Fi/GPS and requires Location Services to be enabled in Windows Settings.
- Skills are installed from GitHub and their instructions are injected into the system prompt. A tamper-check (SHA-256 tree hash) prevents modified skills from loading, but review skill instructions before installing.
- `delete_file` is permanent. There is no trash, no undo. The only barrier is a `y/N` prompt.
- Browser actions that mutate state require user approval, but the approval prompt is a simple `y/N` in the terminal.
- Error handling is functional but not exhaustive.
- The voice pipeline requires `sounddevice`, which can be finicky on Windows depending on audio drivers.
- `smoke.py` provides a 20-scenario automated test suite but it requires a live LLM backend and MCP servers to run. It is not a unit test suite and does not mock the model.
- Conversation recall stores every turn in `recall/chat_log.jsonl` as plain text. Delete the `recall/` folder or use `/forget` to clear it.
- The scheduler persists jobs to `schedules.json`. Jobs survive restarts but are tied to the local clock — if the machine is off when a one-shot reminder fires, it will be spoken on next startup if it missed by less than 1 hour.
- GitHub integration is read-only. `my_prs`, `review_requests`, `my_issues`, and `notifications` require `GITHUB_TOKEN` in `.env`. Notifications require a classic token with the `notifications` scope — fine-grained tokens do not support it.
- Currency conversion uses the Frankfurter API (ECB rates). Not all currency pairs are supported — pairs outside the ECB basket fall back to `web_search`.
- Air quality data is modelled by CAMS via Open-Meteo, not a street-level sensor. Numbers differ from Indian apps that use the CPCB scale.
- `youtube_transcript` requires `youtube-transcript-api` (`uv add youtube-transcript-api`). Transcripts are not available for all videos (disabled captions, private videos, or IP blocks).
- Telegram polling requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Only messages from the configured chat ID are processed. The terminal and Telegram share one agent lock — they do not run concurrently.

---

## Future Improvements

- **Streaming responses** — LLM responses are now streamed token-by-token. The `Stream` class in `voice_out.py` feeds deltas to TTS sentence-by-sentence. End-to-end latency from first token to first audio is already low; further gains are possible by piping the stream directly into the agent reply path.
- **Voice input** — the built-in STT pipeline (`voice_in.py`) requires the Kaggle server to be running. A fully offline replacement (e.g. [Handy](https://github.com/handyai/handy) or a local Whisper model) would make the entire pipeline air-gapped
- **Local OCR** — replace the remote OCR endpoint with a local model (e.g. Tesseract or a local vision LLM) so image reading works fully offline
- **GUI / web interface** — a minimal frontend so this isn't terminal-only
- **Local LLM fallback** — automatic failover to a local model when the remote backend is unreachable
- **Tool sandboxing** — run `run_command` inside a Docker container or Windows sandbox instead of the host shell
- **Tool routing** — activate tool groups (browser, weather, places, docs, OCR) only when the user's message matches relevant keywords, reducing wrong-tool failures as the tool count grows (the skills system already does this for skills via embedding similarity)
- **Multi-agent** — spawn sub-agents for parallelizable research tasks instead of sequential tool calls
- **Persistent sessions** — full conversation history (not just recall snippets) across restarts
- **Wake word** — always-on microphone with a wake word to trigger the agent without typing
- **Plugin system** — skills cover prompt-level plugins; the next step is hot-loadable *tool* modules that register new tool schemas without restarting
- **Emotion-aware TTS** — modulate voice tone based on response content using the emotion vector API

---

## Dependencies

Core: `openai`, `mcp`, `ddgs`, `scrapling`, `sentence-transformers`, `numpy`, `python-dotenv`
RAG: `chromadb`, `pypdf`, `python-docx`
OCR: `pillow`, `httpx`
Weather/Places/Currency/GitHub/Telegram: `httpx`
Sun/Moon: `astral`, `tzdata` (Windows)
YouTube: `youtube-transcript-api`
Skills: `pyyaml`
Browser: `@playwright/mcp` (via npx), `obscura`
Audio: `sounddevice`, `soundfile`, `pocket-tts`, `torch`, `websockets`
Runtime: `uv` (Python 3.14+)

---

*Competence first. Swagger second. Everything else is costume.*
