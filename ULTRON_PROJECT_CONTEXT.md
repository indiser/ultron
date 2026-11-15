<!--
AI-CONTEXT-DOC | project: Ultron | doc-version: 1.2.0 | last-updated: 2026-11-15
Update rules are in SECTION 14. Never overwrite; append.
-->

# ULTRON: Project Context Guide

## 0. How an AI should use this document

You are given this file instead of the source code. Treat it as the source of truth for architecture, behavior, conventions and known problems of the project "Ultron".

Rules for you (the AI reading this):
1. Do NOT invent files, functions, env vars or behavior not listed here. If unsure, say "not in context doc" and ask for the file.
2. Source files NOT included in the original upload (contents unknown): `Sys_Prompt.txt` (persona), `.env`, `memory.md`, `first_voice.safetensors`, dependency manifest (`pyproject.toml`/`requirements.txt`), `workspace/`, `chroma_db/`. See Section 12.
3. When user asks for code changes, give full replacement for the touched function or an exact `old`/`new` edit. Respect conventions in Section 11.
4. When a change adds or alters features, follow Section 14 to update this doc (append-only).
5. When user's request touches a file in detail you cannot reproduce from this doc, ask them to paste that one file only.

---

## 1. One-paragraph summary

Ultron is a local-first, Windows-first, terminal chat agent. It talks to an OpenAI-compatible LLM endpoint (a small open model, currently self-hosted on Kaggle through a Cloudflare tunnel), runs a hand-written tool-calling loop with guardrails, and has tools for: workspace files, shell commands (user-approved), web search (DuckDuckGo), deep web research (fetch 5 pages, embed, rank, extract), RAG over user documents (ChromaDB + bge-small embeddings), browser automation (Playwright MCP over a headless "obscura" CDP browser or a visible browser), persistent memory (`memory.md`), and spoken replies (local TTS via `pocket_tts` with a cloned voice). No agent framework is used; the loop is custom.

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.10+ (uses `X \| None` syntax), asyncio |
| LLM client | `openai.AsyncOpenAI` pointed at custom `base_url`, `api_key="no-api"`, `max_retries=0` |
| LLM (remote) | ~~`xtools-at/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic`, bnb-4bit, `transformers serve`~~ → any model via `SRC` in notebook (GGUF preferred), served by `llama-server --jinja` (llama.cpp, CUDA) on Kaggle GPU0 *(corrected v1.1.0)* |
| Embeddings | `BAAI/bge-small-en-v1.5` (local SentenceTransformer on CPU, or remote via `EMBED_BASE_URL`) |
| Vector DB | ChromaDB `PersistentClient`, collection `docs`, dir `chroma_db/` |
| Web search | `ddgs` (DuckDuckGo) |
| Page fetch | Scrapling MCP (`make_request` tool) |
| Browser | `@playwright/mcp` via `npx`; headless = CDP to `obscura serve` on port 9222; visible = `--isolated` |
| Other MCP | `mcp-server-time` via `uvx` (`get_current_time`) |
| TTS | `pocket_tts` + `sounddevice` + `torch` (1 thread) |
| UI | plain terminal, ANSI colors (`text_ui.py`), tkinter upload window |
| Package mgmt for agent-run scripts | `uv` only (never pip) inside `.venv` |
| Target OS | Windows primary (msvcrt Esc watcher, `cmd.exe`, `npx.cmd`, Segoe UI); Linux/mac partially supported |
| OCR | `zai-org/GLM-OCR` (0.9B VLM), `transformers` `AutoModelForImageTextToText`, runs on Kaggle GPU1, async job API |
| Kaggle hardware | T4 x2 (inferred from two `nvidia-smi` rows), CUDA toolkit 13.0, GCC 13.3 |
| Client libs added | `httpx`, `Pillow` (in `ocr_tool.py`) |

---

## 3. File structure

```
project/
├── main.py              # entry point, REPL, slash commands, startup/shutdown
├── agent.py             # run_agent(): tool-calling loop + guardrails + history trimming
├── config.py            # env, LLM client, paths, safe_path()
├── SYSTEM_PROMPT.py     # build_prompt(): persona + AGENT_RULES template
├── Sys_Prompt.txt       # persona text (NOT UPLOADED, contents unknown)
├── tools.py             # call_tool() dispatcher, LOCAL_TOOLS, GATED, missing_args()
├── tools_schema.py      # TOOL_SCHEMAS (OpenAI function schemas); MCP tools appended at runtime
├── mcp_client.py        # connects MCP servers + browser sessions, registers schemas
├── file_tools.py        # list_files, read_file, write_file, edit_file  (+ delete_file v1.2.0)
├── mem_tools.py         # load_memory, save_memory (memory.md)
├── shell_tool.py        # run_command (approval-gated), venv_env()
├── web_tool.py          # ddg(), web_search()
├── research_tool.py     # research(): multi-page fetch, rank, extract, save list
├── timeline_rows.py     # extract_timeline_rows(): Year|Event table parser
├── rag.py               # ingest/search/read/list/remove docs in ChromaDB
├── embed.py             # get_embedder(): local or remote bge-small
├── ocr_tool.py          # ocr_image tool + ocr_file_sync(): image → Kaggle OCR job → text
├── weather_tool.py      # NEW v1.2.0: get_weather, location helpers (IP lookup, geocode, save/load) [UNVERIFIED applied]
├── places_tool.py       # NEW v1.2.0: find_places via OpenStreetMap Overpass [UNVERIFIED applied]
├── upload_ui.py         # tkinter file picker subprocess
├── interrupt.py         # ask() prompt lock, run_cancellable() Esc-to-cancel (Windows)
├── text_ui.py           # c(kind, text) colors, read_you()
├── voice_out.py         # TTS: speak(), stop(), Stream (unused)
├── huggingface-kaggle-endpoint.ipynb  # Kaggle notebook: serves LLM + embedder via tunnels
├── ultron_kaggle_server.ipynb  # NEW notebook (llama.cpp LLM + embeddings + OCR). Supersedes huggingface-kaggle-endpoint.ipynb
├── memory.md            # (runtime) persistent user facts, one "- fact" per line
├── location.json        # (runtime) saved user location {name, lat, lon, tz, source}. Plain text. Keep out of git.
├── workspace/           # (runtime) sandbox for agent files, flat names only
├── chroma_db/           # (runtime) vector store
├── .venv/               # (runtime) uv venv for agent-run commands
├── .env                 # (NOT UPLOADED) see Section 4
└── first_voice.safetensors  # (NOT UPLOADED) TTS voice prompt state
```

### Import graph (who imports whom)

```
main  → mem_tools, SYSTEM_PROMPT, agent, mcp_client, voice_out, config, rag, interrupt, text_ui
agent → config, tools_schema, tools, text_ui
tools → file_tools, mem_tools, shell_tool, web_tool, mcp_client, research_tool, tools_schema, rag, interrupt
rag   → config, embed, research_tool (fetch_page)
research_tool → embed, config, mcp_client (mcp_session), web_tool (ddg), timeline_rows
shell_tool → config, interrupt (ask)
file_tools, mem_tools, embed → config
tools → ocr_tool (ocr_image)
rag   → ocr_tool (lazy import inside _extract, image branch)
ocr_tool → config (safe_path, WORKSPACE); rag (lazy import of ingest_doc inside ocr_image)
tools → weather_tool (get_weather), places_tool (find_places)
places_tool → weather_tool (load_location, save_location, ip_location, geocode)
main → weather_tool (load_location, save_location, ip_location, geocode) for /loc
file_tools → rag (lazy import of remove_doc inside delete_file)
```
`tools.py` and `shell_tool.py`/`file_tools.py` use `from X import *`. Watch for name collisions when adding module-level names.

---

## 4. Environment and config

`config.py`:
- Forces stdout UTF-8.
- `load_dotenv()`.
- `client = AsyncOpenAI(base_url=BRAIN_LLM_BASE_URL, api_key="no-api", max_retries=0)`
- `MODEL = BRAIN_LLM_NAME`
- `WORKSPACE = <project>/workspace` (auto-created)
- `MEMORY_FILE = <project>/memory.md`
- `VENV = <project>/.venv`
- `EMBED_PATH = "BAAI/bge-small-en-v1.5"`
- `QUERY_PREFIX = "Represent this sentence for searching relevant passages: "` (bge query prefix, applied to queries only, never to documents)
- `safe_path(filename)` resolves inside WORKSPACE, raises `ValueError("path outside workspace")` otherwise.

Env vars:

| Var | Used in | Purpose |
|---|---|---|
| `BRAIN_LLM_BASE_URL` | config.py | OpenAI-compatible LLM endpoint (the Kaggle tunnel URL + `/v1`) |
| `BRAIN_LLM_NAME` | config.py | model id sent in requests |
| `EMBED_BASE_URL` | embed.py | if set, embeddings come from remote `/v1/embeddings`; else local SentenceTransformer |
| `TTS_STATE` | voice_out.py | path to voice prompt `.safetensors` (default `first_voice.safetensors`) |
| `TTS_MAX_CHARS` | voice_out.py | max chars spoken per reply (default 600) |
| `NO_COLOR` | text_ui.py | disable ANSI colors |
| `HF_TOKEN` | Kaggle notebook only | Hugging Face download token (Kaggle secret) |
| `OCR_MAX_SIDE` | ocr_tool.py (client) | max image side px before upload. Default 1024 (first draft 2000) |
| `OCR_JOB_TIMEOUT` | ocr_tool.py | seconds to poll an OCR job. Default 420 |
| `OCR_MODEL` | Kaggle embed_server.py | OCR HF id. Default `zai-org/GLM-OCR` |
| `OCR_MAX_SIDE` | Kaggle embed_server.py | server-side thumbnail cap. Notebook sets 1280 (2 GPUs) or 1024 (1 GPU) |
| `CUDA_VISIBLE_DEVICES` | Kaggle notebook | LLM server = `0`. OCR/embed server = `1` if 2 GPUs else `0` |

Note v1.1.0: `EMBED_BASE_URL` now also hosts OCR. Client builds OCR URL as `EMBED_BASE_URL.rstrip("/") + "/ocr"` then `/start` and `/<id>`. No separate OCR env var.
Note v1.1.0: `BRAIN_LLM_NAME` must equal llama-server `--alias`. Notebook sets alias = HF repo id (or GGUF file stem for local paths) and prints the full `.env` block at the end of cell 8.

Added v1.2.0: `config.py` has `LOCATION_FILE = <project>/location.json`. No new env vars.
External services used without API keys:
- Open-Meteo forecast `api.open-meteo.com/v1/forecast` and geocoding `geocoding-api.open-meteo.com/v1/search`
- IP geolocation `ip-api.com/json` (HTTP only, free tier non-commercial, 45 req/min), fallback `ipapi.co/json`
- OpenStreetMap Overpass `overpass-api.de/api/interpreter` (sends header `User-Agent: UltronAgent/1.0`)
Privacy: first no-arg weather/places call sends your public IP to ip-api.com once. Result cached in `location.json`. Setting `/loc <city>` first avoids any IP lookup.

Required external binaries: `uv`, `uvx`, `npx`, `obscura`, `scrapling` (CLI with `mcp` subcommand).

---

## 5. Runtime flow

### Startup (`main.py: main()`)
1. Launch `obscura serve` subprocess (headless CDP browser). `wait_port(9222)`. Warn if missing, continue.
2. `AsyncExitStack` → `connect_mcp(stack)`: connects `time` and `scrapling` MCP servers, then `connect_browsers` (headless + visible). Allowed MCP tools get registered into `TOOL_SCHEMAS`.
3. Build system message: `build_prompt(memory=load_memory(), today=<iso date>, shell="Windows cmd.exe" or "bash")`.
4. REPL loop: `read_you()` → handle commands → else append user message → `run_cancellable(run_agent(messages))`.
5. On exit: terminate obscura.

Note: `voice_out` loads the TTS model at import time (prints `[tts] loading model...`, runs a warmup generation). Startup is slow because of this.

### REPL commands (handled in `main.py`, not by the LLM)
| Input | Effect |
|---|---|
| `stop`, `/stop`, `quiet`, `enough`, `shut up` | `voice_out.stop()` |
| `/upload` | opens tkinter picker (`upload_ui.py` subprocess), copies to workspace, indexes |
| `/add <path or http url>` | copy+index local file, or `ingest_url` |
| `/docs` | `list_docs()` |
| `/remove <source>` | `remove_doc()` |
| `/loc` | show saved location `[UNVERIFIED applied]` |
| `/loc auto` | re-detect by IP and save `[UNVERIFIED applied]` |
| `/loc <city>` or `/loc <city>, <region>` | geocode and save; text after the comma filters same-name cities `[UNVERIFIED applied]` |
| anything else | goes to agent |

After a successful index, a `pending` list is prepended to the *next* user message as `[system: indexed: ...  Use search_docs or read_doc ...]` so the LLM knows about new docs. If a turn is cancelled (Esc), messages added that turn are deleted (`del messages[n:]`) and `pending` is restored.

Change v1.2.0 `[UNVERIFIED applied]`, forced research routing in `agent.py`:
- Module level: `RESEARCH_RE = re.compile(r"\bresearch(?:ing)?\b", re.I)` and `wants_research(messages)`: finds last user message, strips the `[system: ...]` first line that `main.py` prepends, returns whether the regex matches.
- In `run_agent`: `want_research = wants_research(messages)`, `researched = False`, `r_nudged = False`.
- No-tool-call branch: if `want_research and not researched and not r_nudged` → append assistant text (if any) + user message `User asked for research. Call the research tool now. Do not answer from memory.` and `continue` (once per turn).
- After `args = json.loads(...)`: if `want_research and name == "web_search"` → `name = "research"`, `args = {"query": args.get("query", "")}` (silent remap).
- First guard gets `and not want_research` (research allowed without prior web_search).
- On successful dispatch of `research`: `researched = True`.
- Regex is loose: any message containing "research" forces research. Stricter variant offered: `\b(?:deep[- ]research|research(?:ing)?\s+(?:on|about|into|this|it|the|how|why|what|who|when|where)|(?:do|run|please|can you)\s+research)\b`.
- Research failure is final: no fallback to `web_search`.

Change v1.2.0: after successful `write_file`, `edit_file` or `delete_file` (result starts `wrote`, `edited`, `deleted`) → `seen.clear()`. `[UNVERIFIED applied]` for the `seen.clear()` line itself (delete_file itself works).
Esc cancel works only on Windows (`msvcrt`); on other OS `run_cancellable` just awaits.

### Per-turn agent loop (`agent.py: run_agent(messages)`)
Constants: `MAX_STEPS = 40`, `RESULT_CAP = 8000` chars, `temperature=0.1`, `max_tokens=1500`.

Each step:
1. `trim_history`: if total `str(m)` chars exceed budget, truncate all but last 2 `tool` messages to 300 chars + `" [old result trimmed]"`.
2. `drop_old_turns`: while still over budget and ≥3 user messages, delete everything from first user message up to the second user message (oldest turn).
   - `budget = len(str(messages[0])) + 12000` (system prompt size + 12k chars). Chars, not tokens.
3. Call LLM with `TOOL_SCHEMAS`. On exception return `"error: model call failed: ..."`.
4. No tool calls → return text. If empty text: nudge once (`"Answer now, briefly, from the tool results above."`), else `"(model returned an empty reply)"`.
5. Tool calls → for each call, apply guards (below), execute via `call_tool`, append `{"role":"tool", ...}` result.
6. If last 4 tool results in a row start with `error:` → stop with `"stopped: tools kept failing. ..."`.
7. Loop ends after 40 steps → `"stopped: too many tool steps. ..."`.

Guards inside the loop, evaluated in this order for each tool call:
| Guard | Result string |
|---|---|
| `research` called before any `web_search`/`research` and no `save_to` | `error: call web_search first...` |
| `run_command` and `cmd_fails >= 5` | `error: 5 commands failed. Stop...` |
| identical (name, args) already called, except `run_command`, `browser_snapshot`, `set_browser_mode` | `error: identical call already made...` |
| `missing_args()` non-empty (checks `required` in schema) | `error: <name> missing required args...` |
| else | execute; `result = str(await call_tool(...))[:8000]` |
| `fails[key] >= 2` (same (name,args) failed twice) `[UNVERIFIED applied]` | `error: this exact call failed twice. Change the args or tell the user what is missing.` |

Order note v1.2.0: real evaluation order is research-first guard, `cmd_fails`, `fails[key] >= 2` `[UNVERIFIED applied]`, `seen` duplicate, `missing_args`, execute. The `fails` row in the table above is listed out of order.

`cmd_fails` increments when `run_command` output contains `is not recognized`, `SyntaxError`, `Traceback`, or `was unexpected`. It resets to 0 after a successful `write_file` ("wrote..."). 

Change v1.1.0 `[UNVERIFIED applied]` in `run_agent`:
- `seen` no longer permanent for failures: after a tool result starting `error:`, `seen.discard(key)` and `fails[key] += 1`. Lets legit retry after transient error. Cap 2 per identical call.
- After successful `write_file` or `edit_file` (`wrote` / `edited`), `seen.clear()`. Lets model verify with `read_file` / `list_files`.
- `missing_args` (tools.py) now treats `None` and `""` as missing: `[k for k in required if args.get(k) in (None, "")]`.

Change v1.2.0 `[UNVERIFIED applied]`, forced research routing in `agent.py`:
- Module level: `RESEARCH_RE = re.compile(r"\bresearch(?:ing)?\b", re.I)` and `wants_research(messages)`: finds last user message, strips the `[system: ...]` first line that `main.py` prepends, returns whether the regex matches.
- In `run_agent`: `want_research = wants_research(messages)`, `researched = False`, `r_nudged = False`.
- No-tool-call branch: if `want_research and not researched and not r_nudged` → append assistant text (if any) + user message `User asked for research. Call the research tool now. Do not answer from memory.` and `continue` (once per turn).
- After `args = json.loads(...)`: if `want_research and name == "web_search"` → `name = "research"`, `args = {"query": args.get("query", "")}` (silent remap).
- First guard gets `and not want_research` (research allowed without prior web_search).
- On successful dispatch of `research`: `researched = True`.
- Regex is loose: any message containing "research" forces research. Stricter variant offered: `\b(?:deep[- ]research|research(?:ing)?\s+(?:on|about|into|this|it|the|how|why|what|who|when|where)|(?:do|run|please|can you)\s+research)\b`.
- Research failure is final: no fallback to `web_search`.

Change v1.2.0: after successful `write_file`, `edit_file` or `delete_file` (result starts `wrote`, `edited`, `deleted`) → `seen.clear()`. `[UNVERIFIED applied]` for the `seen.clear()` line itself (delete_file itself works).

Return value convention: strings beginning `error:` are shown red in `main.py` and are NOT spoken. Everything else is printed and spoken via `voice_out.speak`.

---

## 6. Tool registry

Defined in `tools_schema.py` (`TOOL_SCHEMAS`, OpenAI function format). Implemented in `tools.py` (`LOCAL_TOOLS` dict + special cases in `call_tool`).

### Local tools
| Tool | Impl | Notes |
|---|---|---|
| `list_files` | file_tools | names in workspace, `(empty)` if none |
| `read_file(filename)` | file_tools | UTF-8; truncates at 4000 chars with note |
| `write_file(filename, contents)` | file_tools | rejects placeholder patterns like `[Name 6]`, `[Add more...]`, `[List of...]`; returns `wrote: <name>` |
| `edit_file(filename, old, new)` | file_tools | `old` must occur exactly once; returns `edited: <name>` |
| `save_memory(fact)` | mem_tools | appends `- fact` to `memory.md`; only when user asks |
| `run_command(command)` | shell_tool | user types `y` to approve each; cwd=workspace; 120 s timeout; runs inside `.venv` env (`venv_env()` auto-creates with `uv venv --seed`); returns last 3000 chars; blocks `python -c "...; for/with/if/while/def"` |
| `web_search(query)` | web_tool | 5 results: title, URL, snippet |
| `research(query, save_to="")` | research_tool | async, see Section 7 |
| `set_browser_mode(mode)` | tools | `headless` or `visible`; state lost on switch |
| `ingest_doc(filename)` | rag | index a workspace file |
| `search_docs(query, source="")` | rag | top 4 chunks, 800 chars each |
| `read_doc(source, part=1)` | rag | 3 chunks per part |
| `list_docs` | rag | per source: chunks, parts |
| `upload_doc` | rag | spawns tkinter picker |
| `ingest_url(url)` | rag (async) | download page/PDF to workspace and index |
| `remove_doc(source)` | rag | GATED (asks y/N) |
| `ocr_image(filename)` | ocr_tool (async, special-cased in `call_tool` like `ingest_url`) | image in workspace (png jpg jpeg webp bmp). If name not found and exactly one image exists in workspace, uses that image. Else error lists real image names. Saves `<stem>.ocr.md`, cached by mtime. Runs `rag.ingest_doc` on it. Returns `DONE. OCR text saved to X.ocr.md, N chars. indexed: ... Preview: <300 chars>. Use search_docs or read_doc for details.` Full text NOT returned (context budget). |
| `delete_file(filename)` | file_tools | files only, never folders. `safe_path` (workspace only). `path.unlink()`, then lazy `rag.remove_doc(filename)` (errors ignored) so index chunks go too. Returns `deleted: <name>`. Errors: `error: no file named X`, `error: X is not a file. Folders are not deleted.` GATED: user types `y`. No undo, no trash. |
| `get_weather(location="", days=3)` | weather_tool (async, special-cased in `call_tool`) | current + daily forecast 1–7 days from Open-Meteo. Empty location = saved location (first use: IP lookup, saved to `location.json`). Named location = one-shot geocode, NOT saved. Output header names the place and location source. Errors: `error: location failed: ... Ask the user for a city name.`, `error: weather request failed: ...`. `[UNVERIFIED applied]` |
| `find_places(category, near="", radius_km=2, limit=8)` | places_tool (async, special-cased) | OSM Overpass. `category` is a schema enum: restaurant cafe fast_food bar hospital pharmacy atm bank fuel hotel museum attraction park supermarket airport railway_station bus_station. Radius clamped 0.2–20 km, limit 1–15. Sorted by haversine distance. Unnamed elements skipped. Output: name, km, address, cuisine, hours, phone. No ratings (OSM has none). Errors: `error: unknown category`, `error: map server busy. Tell the user to retry in a minute.` (HTTP 429/504). `[UNVERIFIED applied]` |

### MCP tools (registered at runtime in `mcp_client.py`)
- `get_current_time` from `mcp-server-time`.
- `make_request` from Scrapling: allowed but HIDDEN (not given to LLM). Used internally by `research_tool.fetch_page`.
- Browser (Playwright MCP) allowed set: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_wait_for`. Schemas are registered once, from whichever browser session connects first; calls route to `browser_sessions[browser_state["mode"]]`. Output capped at 8000 chars.

### Confirmation gating (`tools.py: GATED`)
`browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `remove_doc` → `ask("Confirm ...? [y/N]")`. `run_command` has its own prompt. `interrupt.ask()` sets a threading event so the Esc watcher doesn't steal keystrokes during the prompt.

Change v1.2.0: `GATED` now also contains `delete_file`. The decline text in `call_tool` changed from `The user declined this browser action` to `The user declined this action`.

### Dispatch order in `call_tool`
GATED check → `research` → `ingest_url` → `LOCAL_TOOLS` → `browser_navigate` w/o url error → `browser_*` → other MCP via `mcp_session[name]` (output capped at 5000).

Update v1.2.0: async special cases before `LOCAL_TOOLS` are now `research`, `ingest_url`, `ocr_image`, `get_weather`, `find_places`. `delete_file` is a sync entry in `LOCAL_TOOLS`.

Change v1.1.0 `[UNVERIFIED applied]`: `mcp_client.py` gets `clean_schema()` (drops `$schema` and `additionalProperties`, ensures `type`, `properties`, `required`). `browser_navigate` schema forced to `required: ["url"]` with a `url` property. Tool descriptions cut to 200 chars. `tools.py` empty-url error text: `error: browser_navigate needs url. Resend exactly: {"url": "https://en.wikipedia.org/wiki/India"} with the real link.`



---

## 7. Research pipeline (`research_tool.py`)

`research(query, save_to="", top_k=3)`:
1. `ddg(query, 8)` → take first 5 results.
2. `fetch_page(url)` for all 5 concurrently (Scrapling `make_request`, 25 s timeout, `clean_markdown`, capped 150k chars). Pages under 300 chars are dropped.
3. `chunk_markdown` (size 800, overlap 100, max 120 chunks/page).
4. `score_pages`: embed query (with prefix) and chunks.
   - `best_sim` = mean of top 3 chunk similarities.
   - `pagerank` over page-to-page similarity matrix (mean chunk vectors; edges = similarity minus median, clipped).
   - `rrf` = `1/(60+search_rank)`.
   - `final = 0.45*minmax(best_sim) + 0.25*minmax(pagerank) + 0.30*minmax(rrf)`, then multiplied by `(1 - 0.6*junk_ratio)`; junk = share of lines that are table rows or `1. ↑` style refs.
5. Mode A, no `save_to`: return `Best source: <url>`, other sources, top 2 chunks of best page + best chunk from pages 2 and 3, plus numbered items if ≥5 found.
6. Mode B, `save_to` set: for each ranked page try, in order, `extract_table_rows` (rank + name + big number), `extract_items` (numbered list `1. 2. 3.`), `extract_timeline_rows` (`| YYYY | event |`). `want` is parsed from query ("top 10", "50 largest"; default 10); `need = max(5, 0.8*want)`. For `.csv` targets, items must contain large numbers (`\d{1,3}(,\d{3}){2,}` or 7+ digits) or are dropped. On success write file and return `DONE. All N items saved to <file>. Source: ...`. CSV columns: `rank,name,value`. TXT format: `1. item`. Else `error: no ranked page had a clean numbered list...`.

`web_tool._variants(q)`: tries original query, a variant with "today"/"to today"/"until today" replaced by the literal `2026`, and a stripped version (removes words deep/research/major/list/all, first 6 words). First variant that returns results wins. Each tried twice with 1.5 s sleep.

---

## 8. RAG pipeline (`rag.py`)

- Store: Chroma collection `docs`; ids = md5(`source:index`); metadata `{source, label, idx}` (`label` = `p.N` for PDFs, else empty).
- Extract: `.pdf` (pypdf, per page), `.docx` (python-docx: paragraphs + tables), `.doc` rejected, everything else read as text.
- Split: sentence-aware, `size=900`, `overlap=150`, drops chunks ≤40 chars.
- Embedding: `get_embedder().encode(..., normalize_embeddings=True, batch_size=16)`, re-normalized. Queries get `QUERY_PREFIX`.
- Index batches of 64. Re-ingesting a source deletes the old chunks first (`_col.delete(where={"source": ...})`). Scanned PDF with no text → `error: no text in X. Scanned PDF? Needs OCR.`
- `search_docs`: top 4, optional `source` filter. Output: `[source label]\n<first 800 chars>`.
- `read_doc(source, part)`: chunks sorted by `idx`, 3 per part, header `[source part N/total, p.X to p.Y]`.
- `ingest_url`: httpx GET; PDFs saved as `.pdf`, pages fetched through Scrapling → saved `.md` → `ingest_doc`. File name = sanitized netloc+path, max 60 chars.
- `upload_doc`: runs `upload_ui.py` via `subprocess.run([sys.executable, ...])`, 300 s timeout, last stdout line is JSON list of paths.

Embeddings location: `embed.get_embedder()` is a lazy singleton. If `EMBED_BASE_URL` set → `RemoteEmbedder` (OpenAI client; `encode()` mimics SentenceTransformer API, returns 1-D array for single string). Else local `SentenceTransformer(EMBED_PATH, device="cpu")`; raises `RuntimeError` with a download hint if not cached.

Change v1.1.0: `_extract` has an image branch. Extensions `.png .jpg .jpeg .webp .bmp` → `ocr_tool.ocr_file_sync(path)` → `[("", text)]`. So `/add pic.png` and `/upload` index images via OCR. OCR errors surface as `error: RuntimeError: ...` from `ingest_doc`. `upload_ui.py` filetypes include images. Scanned-PDF OCR NOT implemented (error text still says "Needs OCR").
---

## 9. System prompt (`SYSTEM_PROMPT.py`)

`build_prompt(memory, today, shell)` = `PERSONA.strip() + "\n\n" + AGENT_RULES` with `{today}`, `{shell}`, `{memory}` string-replaced.

- `PERSONA` is read from `Sys_Prompt.txt` (a commented-out alternative reads `Main_Prompt.txt`). Contents not in this doc.
- `AGENT_RULES` sections: header saying tool rules override persona and persona applies to final reply text only; Runtime block (name unknown, date, shell, prompt disclosure OFF, memory dump); Tool list with usage hints; Workflow (Triage → Investigate → Act → Verify → Report, "cheapest path"); Rules list.
- Key behavioral rules encoded: never invent data; never answer current facts from memory; one question per search; check source scope matches question; saved item count must match request; "DONE. All N items saved" means complete; use `uv` not `pip`; Windows has no awk/sed/cat/grep; write `.py` script instead of `python -c` with control flow; do not ask user to choose between options; no destructive commands unasked.
- Memory is injected ONCE at startup. `save_memory` writes to disk but the live system prompt is not refreshed until restart.

Change v1.1.0 `[UNVERIFIED applied]`, added to `AGENT_RULES`:
- Tools list: `ocr_image: read text from an image file in the workspace. Saves <name>.ocr.md and indexes it. Then use search_docs or read_doc. Text only. Never guess image content. Cannot describe photos.`
- Tools list: `browser_navigate: always pass url, a full https link. Wikipedia page: https://en.wikipedia.org/wiki/<Title>.`
- Workflow triage: `Image or screenshot to read: ocr_image, then search_docs or read_doc.`
- Rules: `Never invent file names. Copy names exactly from list_files. Not sure: call list_files.`
- Tool schema for `ocr_image.filename`: description `File name copied exactly from list_files output.` (no example name, examples bias the model into copying them)

Change v1.2.0, added to `AGENT_RULES` (all `[UNVERIFIED applied]` except delete_file line, which user confirmed working):
- Tools list: `delete_file: delete one workspace file. User approves each call. Only when the user asks to delete. Copy the name exactly from list_files. Never delete to "clean up" on your own.`
- Tools list, `research` line extended: `User says "research" or "deep research" in any form: ALWAYS this tool, never web_search.`
- Workflow triage, FIRST bullet: `User says "research" or "deep research": call research first. Never web_search. This overrides the cheapest-path rule.`
- Rules: `Explicit research request: web_search is forbidden for that turn. Several subjects: one research call per subject.`
- Tools list: `get_weather: current weather and forecast. No location arg = user's saved location. Never web_search for weather.`
- Triage: `Weather, temperature, rain, forecast: get_weather, then answer.`
- Rules: `Weather answer: say which place it is for, using the place name from the tool result.`
- Tools list: `find_places: nearby places by category, sorted by distance. No ratings. Empty near = saved location. Never web_search for "near me".`
Schema text changes: `research` description says "Always use when the user says research or deep research."; `web_search` description appended "Never use when the user asks for research or deep research."

---

## 10. Remote LLM and embedding server (Kaggle notebook)

`huggingface-kaggle-endpoint.ipynb` cells in order:
1. `pip install "transformers[serving]" accelerate bitsandbytes`
2. Download model `xtools-at/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic` with `snapshot_download` (ignores gguf/pth/original). Uses Kaggle secret `HF_TOKEN`. Contains an `assert MODEL != "<same repo id>"` placeholder guard: with `MODEL` set to that exact id the assert fails, so the guard must be edited/removed when the model is set.
3. Start `transformers serve --port 8000 --quantization bnb-4bit --model-timeout 43200`; poll `/v1/models`; warmup chat; stress test with ~2500-word prompt. GPU memory observed ~5 GB of 15 GB.
4. Download `cloudflared`, quick tunnel to `localhost:8000` → prints `BASE URL: https://<random>.trycloudflare.com/v1`.
5. Install `fastapi uvicorn sentence-transformers`.
6. Write `embed_server.py` (FastAPI `POST /v1/embeddings`, bge-small on CPU, `max_seq_length=256`, normalized, returns OpenAI-style payload with `usage` zeros).
7. Run uvicorn on 8001 + second cloudflared tunnel → prints `EMBED URL: https://<random>.trycloudflare.com/v1`.

Workflow each session: run notebook → copy `BASE URL` to `BRAIN_LLM_BASE_URL` and `EMBED URL` to `EMBED_BASE_URL` in `.env` → restart Ultron. Quick-tunnel URLs are random and change every run. Kaggle sessions are time-limited.

Note: the remote embedder truncates at 256 tokens, but `rag` chunks are 900 chars (~200 tokens) and research chunks 800 chars, so mostly fine.

### 10.1 New notebook `ultron_kaggle_server.ipynb` (v1.1.0). Supersedes cells 1–3 above.

Why: `transformers serve` + bnb-4bit was slow (45–75 s per LLM step), hit Cloudflare 120 s limit, no prompt cache, and OCR OOM'd sharing GPU. Old assert guard bug (`assert MODEL != <same id>`) is moot.

Cells in order:
1. `pip install -U transformers accelerate huggingface_hub fastapi uvicorn sentence-transformers pillow requests`
2. Config. Edit `SRC`, `NON_GGUF`, `CTX` (16384), `THINK` (False). Loads `HF_TOKEN` secret if present. Detects GPUs via `nvidia-smi`. Sets LLM on GPU0, OCR/embed on GPU1 (if 2 GPUs). Defines `sh()` (logs to `notebook.log`, raises with log tail).
3. Get `llama-server` binary. Order: cached → prebuilt tarball (`ai-dock/llama.cpp-cuda` latest release, asset `cuda-12.8-amd64`) + pip `nvidia-cuda-runtime-cu12 nvidia-cublas-cu12` installed with `--no-deps --target /kaggle/working/cu12libs` and added to `LD_LIBRARY_PATH` → else build from source (`-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=<sm> -DLLAMA_CURL=OFF`, target `llama-server`). Binary accepted only if `--list-devices` output contains `CUDA` (guards silent CPU run). `ld_path(BIN)` builds `LD_LIBRARY_PATH` for later launch.
4. Resolve `SRC` → `(KIND, PATH, ALIAS, REPO)`.
5. Launch LLM, tests (warmup, 2500-word prompt twice to show prompt-cache speedup, tool-call test, GPU offload log lines, `nvidia-smi`).
6. Cloudflare tunnel for port 8000 → prints `BASE URL`.
7. `%%writefile embed_server.py` (embeddings + OCR).
8. Launch uvicorn port 8001 (`CUDA_VISIBLE_DEVICES=<OCR_GPU>`), tunnel, OCR sanity test (expects `{'status': 'done', 'text': 'OCR TEST 12345'}`), prints `.env` block.

`SRC` forms: `org/name` (auto GGUF pick, preference Q4_K_M, Q4_K_S, IQ4_XS, Q4_0, Q5_K_M, Q5_K_S, Q6_K, Q8_0, Q3_K_M; handles split shards; skips `mmproj`) | `org/name:QUANT` | `org/name/file.gguf` | local path (file or folder).
Size guard: GGUF GB must be under `VRAM_GB*0.85 - 2.5` of GPU0, else error before download.
Repo with no `.gguf` but safetensors / `pytorch_model*.bin`: `NON_GGUF="convert"` runs llama.cpp `convert_hf_to_gguf.py --outtype q8_0` (needs RAM ~ model size; unsupported arch fails) or `"transformers"` = old bnb-4bit `transformers serve`. Repo with only `.pth`: unsupported, raises error.
llama-server args: `-m PATH --alias ALIAS -ngl 999 -c CTX -np 1 --jinja --host 127.0.0.1 --port 8000`, plus `--reasoning-budget 0` tried first when `THINK=False`, auto-retry without if server rejects.
Source-build fix for Kaggle CUDA 13: CMake error `CUDA::cuda_driver ... target was not found` solved by symlinking a `libcuda.so` (toolkit stub or driver `libcuda.so.1`) into `/kaggle/working/stubs` and passing `-DCUDA_CUDA_LIBRARY=<link> -DCMAKE_LIBRARY_PATH=<dir>`; old `build/` dir wiped first.
Prebuilt binary error `libcudart.so.12: cannot open shared object file` = Kaggle has CUDA 13 only; fixed by the cu12 pip libs above.
P100 (sm 60) cannot compile with CUDA 13. T4 (sm 75) fine.

Per-session ritual: run all cells → copy printed `.env` block (`BRAIN_LLM_BASE_URL`, `BRAIN_LLM_NAME`, `EMBED_BASE_URL`) into local `.env` → restart Ultron. Tunnel URLs change every run.
---

## 11. Conventions and design principles

Behavioral and code conventions the project follows. Keep them when adding features.

1. Tools return plain strings. Errors start with `error:`. Success markers matter: `wrote:`, `edited:`, `indexed:`, `DONE.`, `saved:`. The loop and the prompt key on these prefixes.
2. Tool-result text is written as instructions to a small LLM ("Resend the full call with all args", "Change the query or approach"). Keep messages short and imperative.
3. Guardrails live in code (`agent.py`), not only in the prompt. The model is small and weak; assume it will loop, repeat calls, hallucinate args. Prefer a code guard over a prompt rule.
4. Everything the LLM can do is flat and sandboxed: workspace files only, flat names, no paths.
5. Dangerous actions need human `y`: `run_command`, browser input actions, `remove_doc`.
6. Token-saving by design: `RESULT_CAP`, old tool result trimming, schema descriptions short, `max_tokens=1500`.
7. Simple code over abstractions. No framework. System prompt tells the model "prefer simple readable code, no extra features".
8. Colors via `c("<kind>", text)`; kinds: you, assistant, think, tool, result, error, info.
9. Windows is the main target; keep cross-platform branches (`os.name == "nt"`) where they exist.
10. Commented-out old code is left in place in several files (`agent.py`, `main.py`, `web_tool.py`, `research_tool.py`). It is history, not live code.
11. Prefer `enum` parameters in schemas (e.g. `find_places.category`) so the small model cannot invent values.
12. A prompt rule is a request, a code guard is a fact. Anything that must always happen (forced `research`, delete approval) lives in `agent.py` / `tools.py`, prompt only repeats it.
13. Tool count is a budget. Every added tool lowers wrong-tool and empty-args reliability of the 9B model. See Section 13 item 30 and roadmap (tool routing).
14. Location-aware tools resolve place in one order: explicit arg → saved `location.json` → IP lookup (then saved).

### Recipe: add a new tool
1. Write function (sync returns `str`, or async and special-case in `call_tool`).
2. Add to `LOCAL_TOOLS` in `tools.py` (or special-case before it if async).
3. Add schema dict to `TOOL_SCHEMAS` in `tools_schema.py`; put required args in `required` (the `missing_args` guard uses it).
4. Document it in the Tools section of `AGENT_RULES` in `SYSTEM_PROMPT.py` and add triage rules if needed.
5. If it has side effects, add to `GATED` in `tools.py`.
6. If its duplicate calls are legitimate, add to the exemption tuple in the `seen` check in `agent.py`.
7. Update this doc (Section 6 + Changelog).

### Recipe: add a new MCP server
Add to `MCP_SERVERS` in `mcp_client.py`, add tool names to `ALLOWED` (and `HIDDEN_TOOLS` if internal only). Schemas auto-register.

### Recipe: add a REPL slash command
Add an `if cmd == ...` branch in `main.py` before the `held = list(pending)` line.

---

## 12. Unknowns (not in the upload)

| Item | Status |
|---|---|
| `Sys_Prompt.txt` persona text | unknown, ask user to paste if persona work is needed |
| `.env` values | unknown (do not request secrets; tunnel URLs are ephemeral) |
| `memory.md` contents | runtime data |
| Dependency list | inferred: `openai`, `python-dotenv`, `mcp`, `chromadb`, `numpy`, `sentence-transformers`, `pypdf`, `python-docx`, `httpx`, `ddgs`, `torch`, `sounddevice`, `pocket_tts` |
| TTS voice file | `first_voice.safetensors`, user-made |

---

## 13. Known issues, risks and weak points (audit as of v1.0.0)

Ordered roughly by impact. Fix or acknowledge before piling on features.

1. Duplicate-call guard blocks legitimate repeats. `seen` rejects identical `(name, args)` for everything except `run_command`, `browser_snapshot`, `set_browser_mode`. Example: `read_file` after `edit_file` to verify returns `error: identical call already made`; `list_files` after writing a file likewise; `browser_navigate` to same URL after switching modes (system prompt demands this). Consider clearing `seen` on any successful write/edit, or exempting `read_file`, `list_files`, `browser_navigate`.
 **[FIXED in v1.1.0]** `[UNVERIFIED applied]` see Section 5 change note.
2. Blocking sync tools freeze the event loop. `run_command`, `upload_doc` (`subprocess.run`), `ingest_doc`, `search_docs`, `web_search` (DDGS) run synchronously inside async `call_tool`. Esc cancel (`task.cancel`) only fires at the next `await`, so Esc does nothing during these. Fix: `await asyncio.to_thread(...)` for sync tools (careful: `ask()` uses `input()`).
3. Conflicting prompt rules about document summaries. `AGENT_RULES` says `read_doc part 1, 2, 3 in order, max 6 parts` in the Tools section, and later `part 1, then one middle part, then the last part. Max 3 parts.` Small models will pick randomly. Delete one.
4. Prompt vs code mismatch on contradictory instructions: prompt says "Do not ask the user to choose between options" while also expecting confirmations in tool flow. Low risk, but keep consistent.
5. Context budget measured in characters of `str(m)` (including Python object reprs of pydantic messages). `budget = system_len + 12000` chars is tiny (~3k tokens of history). Deep research and RAG results (up to 8000 chars each) are trimmed to 300 chars after two newer tool messages. Long multi-step tasks will lose evidence. Token-based accounting would be better.
6. `drop_old_turns` removes whole oldest turn(s) but never touches the current turn; if the current turn alone exceeds budget it just returns (`len(user_idx) < 3`) and the request may overflow the model context.
7. Hard-coded year: `web_tool._variants` replaces "today" with `"2026"`. Will silently go stale. Use `date.today().year`.
8. Memory is not refreshed live: `save_memory` appends to file, but system prompt keeps the old memory until restart. No dedupe, no cap, no edit/delete tool; memory grows unbounded into every prompt (which also inflates `budget`).
9. Remote infra is fragile: quick Cloudflare tunnels change URL each run; `.env` must be edited by hand; Kaggle session timeouts kill the agent mid-use; `max_retries=0` means one transient failure aborts the turn. Add retry/backoff and a health check at startup.
10. Startup cost: `voice_out` loads TTS and generates a warmup at import time even if you never use voice; `connect_mcp` and `obscura` startup are serial. No lazy loading.
11. Security: `run_command(shell=True)` with user `y/N` is the only barrier; the command string comes from a small, uncensored model and can be prompt-injected through web pages/documents it reads (research, browser, RAG). Approval prompts show the command, so read before pressing `y`. `GATED` omits `browser_navigate` (can exfiltrate data via URLs) and `browser_snapshot`.
12. `safe_path` is correct for traversal but `list_files` lists everything including subdirectories as names; `write_file` has no size limit.
13. `edit_file`/`write_file` placeholder regex only catches a few patterns.
14. `research_tool` assumes tables/lists with specific shapes (rank + number; `1.` lists; year tables). Other list pages silently return `error: no ranked page ...`. CSV path requires large numbers.
15. Duplicated imports and star imports (`from config import *` etc.) hide dependencies; `voice_out.Stream` and `prewarm` are dead code; `trim_history` has a local variable `c` that shadows the imported `c()` colorizer inside that function only.
16. No tests, no logging to file (prints only), no packaging manifest in upload.
17. Windows-only niceties (Esc cancel, `cmd.exe`, tkinter Segoe UI) mean Linux/mac behavior is untested.
18. Model is a 9B 4-bit model with `temperature=0.1` and 1500 max output tokens. Long file writes (`write_file contents`) can be cut off mid-JSON by `max_tokens`, giving malformed tool args.

19. Cloudflare quick tunnel kills any request with no response for ~120 s (`524`, `origin_response_timeout`). Hit LLM steps and first OCR call. Mitigated: async OCR job + polling, llama.cpp speed. NOT fixed: agent LLM calls are non-streaming (`stream=True` TODO, Section 17).
20. Tunnel URLs change every Kaggle run; `.env` edited by hand; Kaggle session limits still kill the agent mid-use.
21. Small model invents file names (`image1.png`, `image2.png`) after `list_files` already returned real names. Mitigation: `ocr_image` auto-picks the only image, error lists real names, prompt rule, schema description without example `[UNVERIFIED applied]`. Residual risk stays. Code guards beat prompt rules.
22. Model sends `browser_navigate({})` with empty args, loops until `errs >= 4` abort. Causes: `missing_args` checked key presence only; Playwright schema may lack `required`; weak model with many tools. Fixes in Section 6 and 5 notes `[UNVERIFIED applied]`. Debug script `dbg.py` decides whether model or schema is at fault.
23. OCR calls GLM-OCR directly, no layout stage (official stack adds PP-DocLayoutV3 layout analysis + parallel recognition). Dense multi-column pages weaker. Prompt used: `Text Recognition:`. Other prompt type (JSON info extraction) not wired.
24. OCR OOM history: image 2000 px → `OutOfMemoryError ... Tried to allocate 24.24 GiB` (vision attention). Fixed by thumbnail cap on client (1024) and server (1280/1024), dedicated GPU1, `empty_cache()` after each job. Cap numbers are estimates; lower `OCR_MAX_SIDE` if OOM returns. OOM error text tells model not to retry.
25. Brain model is text-only. "What is in this photo" unsupported. OCR gives text only. Switching brain to a VLM would need `image_url` content parts and breaks char-based `trim_history` / `budget` math (base64).
26. Tool calling depends on model chat template under `llama-server --jinja`. Cell 5 prints `TOOL CALLS OK` or `TOOL CALLS FAILED`. Failed = do not run Ultron on that model.
27. `torch_dtype="auto"` for GLM-OCR may pick bf16 on T4 (no native bf16). Sanity test passed. If garbage output, use `torch.float32`.
28. `delete_file` has no undo and no trash. Only barrier is the `y/N` prompt, which shows `{'filename': ...}`. Prompt-injected documents/web pages can try to cause a delete; model can guess names (guess → `error: no file named X`, nothing deleted). `<stem>.ocr.md` from an image survives deleting the image and stays indexed under its own name; delete it separately.
29. Location accuracy: IP geolocation is city/ISP-hub level. Indian ISPs often resolve to a hub city. `location.json` goes stale if user moves; no auto-refresh. Fix by `/loc <city>`. First IP lookup leaks public IP to ip-api.com.
30. Tool count dilution: ~30+ tools (Playwright schemas are large). Wrong-tool and empty-args failures (items 21, 22) rise with each tool added. Not mitigated yet. Planned fix: tool routing in `agent.py` (core tools always, group tools only when user message keywords match or group used earlier in chat).
31. OSM data via Overpass: no ratings/reviews, patchy small-shop coverage in India, public server rate limits (429/504). `find_places` is a nearby-lookup, not a review service.
32. Forced research regex (`RESEARCH_RE`) is loose: "explain my research paper" also forces `research`. Each forced `research` costs 30–90 s plus embedding calls to Kaggle. `[UNVERIFIED applied]`
33. Travel planning facts (checked 2026-11-15, web search): Amadeus Self-Service portal decommissioned 17 July 2026, keys deactivated (enterprise contracts only). Kiwi Tequila invitation-only. Skyscanner Flights API partner-gated. Duffel offers search + booking via self-serve signup but test mode returns sandbox data, not real fares. Scrape-style options (Google Flights actors on Apify, Ignav) exist, unofficial or vendor-claimed, free tiers unknown. No free official real-fare API for hobby use.
34. Booking safety: letting the agent pay is NOT allowed by design (weak model, hallucinated args seen in items 21, 22, prompt injection, no undo). Agreed design: agent searches and returns options plus a deep link (Google Flights / airline URL from IATA codes + dates); human clicks and pays.

---

## 14. HOW TO UPDATE THIS DOCUMENT (instructions for any AI)

Goal: keep this file accurate as the project grows WITHOUT losing history.

### Hard rules
1. NEVER rewrite, reorder, shorten or delete existing content. Only: (a) append, (b) make a minimal in-place correction marked as below.
2. Always give the user ONLY the new/changed pieces as copy-paste blocks, plus the exact place to insert them, unless the user asks for the full file. Do not regenerate the whole file.
3. Every change gets a Changelog entry (Section 15), newest at the bottom. No change without an entry.
4. Bump `doc-version` in the first-line comment: patch (x.y.Z) for corrections, minor (x.Y.0) for new features/files/tools, major (X.0.0) for architecture rewrites. Update `last-updated`.
5. Never put secrets (API keys, tokens, live tunnel URLs, `.env` values) in this file.
6. Do not claim something exists unless the user confirmed it in code. Mark uncertain items `[UNVERIFIED]`.

### What to update, by type of change
| Change | Update |
|---|---|
| new/removed file | Section 3 tree + import graph |
| new env var | Section 4 table |
| change in loop, guards, limits | Section 5 |
| new/changed/removed tool | Section 6 table, Section 11 recipes if process changed, and Section 9 if the prompt changed |
| new pipeline (e.g. new retrieval method) | add NEW section at end of numbered sections as `## 16+` (do not renumber existing) |
| bug fixed | Section 13: do NOT delete the item; append `**[FIXED in vX.Y.Z]**` to it |
| new bug/risk found | Section 13: append new item at the end |
| prompt text changes | Section 9 (summarize) and Changelog |
| roadmap | Section 17 |

### Marking corrections
Inline correction format, keep the old text:
`~~old text~~ → new text *(corrected vX.Y.Z)*`

### Procedure
1. Read Section 0, then the sections touched by the change.
2. Produce the minimal additions/edits.
3. Add the Changelog line.
4. Bump version comment.
5. Tell the user exactly where each block goes.

### If the user pastes a new file or diff
Compare to Section 3/6; list differences you found; then apply the procedure.

---

## 15. Changelog (append only, newest at bottom)

| Version | Date | Change | Sections touched |
|---|---|---|---|
| 1.0.0 | 2026-11-15 | Initial doc generated from full codebase upload (20 files) | all |
| 1.1.0 | 2026-11-15 | Added OCR (`ocr_tool.py`, `ocr_image`, async job API on Kaggle, image branch in `rag._extract`). New Kaggle notebook `ultron_kaggle_server.ipynb`: llama.cpp `llama-server --jinja`, GGUF/safetensors/model-id loader, 2-GPU split, CUDA 13 workarounds. Agent guard changes `[UNVERIFIED applied]`, browser schema cleanup `[UNVERIFIED applied]`, prompt additions `[UNVERIFIED applied]`. Known issues 19–27 added. | 2, 3, 4, 5, 6, 8, 9, 10.1, 13, 16.1 |
| 1.2.0 | 2026-11-15 | Added `delete_file` (file_tools, GATED, schema, prompt). Forced research routing in `agent.py` `[UNVERIFIED applied]`. Added `weather_tool.py` (`get_weather`, location helpers, `/loc` command, `location.json`) `[UNVERIFIED applied]`. Added `places_tool.py` (`find_places`, OSM Overpass) `[UNVERIFIED applied]`. Documented travel-search API landscape and no-agent-booking decision. Fixed 1.1.0 paste slips (stray changelog row, missing 16.1, guard order note). Known issues 28–34 added. | 3, 4, 5, 6, 9, 11, 13, 16.1–16.4, 17 |
<!-- APPEND NEW CHANGELOG ROWS ABOVE THIS LINE, KEEP TABLE FORMAT -->

---

## 16. Reserved: new sections go here (numbered 16+ as needed)

<!-- AIs: add new feature sections below this line, one `## N. Title` per feature -->

## 16.1 OCR (v1.1.0)

Server (Kaggle, `embed_server.py`, same tunnel as embeddings):
- `POST /v1/ocr/start` body `{image: <base64>, prompt: "Text Recognition:", max_new_tokens: 1024}` → `{id}`. Starts background thread, returns at once (avoids 120 s tunnel limit).
- `GET /v1/ocr/{id}` → `{status: "running"}` | `{status: "done", text}` | `{status: "error", error}` | `{status: "missing"}`.
- Model `zai-org/GLM-OCR`, preloaded in a thread at server start, one job at a time (`threading.Lock`), `thumbnail((MAX_SIDE, MAX_SIDE))`, `torch.cuda.empty_cache()` in `finally`. Job store keeps last 50.
- `/v1/embeddings` unchanged (bge-small, CPU).

Client (`ocr_tool.py`):
- `ocr_file_sync(path, prompt="Text Recognition:")`: `_prep` (EXIF transpose, RGB, downscale to `OCR_MAX_SIDE`, JPEG q90, base64) → POST `/start` (3 tries, 2 s apart; 404 → "OCR route missing on server. Re-run Kaggle embed_server cell.") → poll every 3 s up to `OCR_JOB_TIMEOUT`. Poll network errors ignored (tunnel blips). `status=error` containing `OutOfMemory` → RuntimeError telling model not to retry. `status=missing` → "OCR job lost, server restarted?".
- `ocr_image(filename)` async tool. Steps: `safe_path`; file check with single-image auto-pick; extension check; cache `<stem>.ocr.md` (reuse if newer than image); else `asyncio.to_thread(ocr_file_sync)`; empty text → `error: no text found in X.`; write `.ocr.md`; lazy `from rag import ingest_doc`; return `DONE...` with 300-char preview.
- Rule: OCR text goes to file + RAG, not chat. History budget is `len(system) + 12000` chars; one dense page is 3–6k chars.

Limits: text only, no layout stage, no scanned-PDF OCR, needs Kaggle session alive.

## 16.2 Weather and location (v1.2.0)

Files: `weather_tool.py`, `config.LOCATION_FILE`, `/loc` in `main.py`.
- `load_location()` / `save_location(loc)`: JSON file `location.json`, shape `{name, lat, lon, tz, source}`; `source` is `ip` or `manual`.
- `geocode(place)`: Open-Meteo geocoding, top 10 results, splits input on commas; first part is the name query, later parts must appear in `admin1/admin2/country` of the chosen hit (else first result). Raises `ValueError("place not found: X")`.
- `ip_location()`: `ip-api.com` (fields status,message,city,regionName,country,lat,lon,timezone), fallback `ipapi.co`. Raises `ValueError` with last reason.
- `get_weather(location="", days=3)`: `days` clamped 1–7. Location order: arg (geocode, not saved) → saved file → IP (saved). Calls Open-Meteo `current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m`, `daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max`, `timezone=auto`. WMO code → text via `WMO` dict. Units: C, km/h, mm. Output starts with `Weather for <place> (location source: <src>), timezone <tz>`.
- Not injected into system prompt and not in `memory.md`.

## 16.3 Nearby places (v1.2.0)

File: `places_tool.py`. `find_places(category, near="", radius_km=2, limit=8)`.
- `OSM` dict maps category → tag (`amenity=restaurant`, `tourism=hotel`, `leisure=park`, `shop=supermarket`, `aeroway=aerodrome`, `railway=station`, ...).
- Query: `[out:json][timeout:25];nwr["k"="v"](around:<m>,<lat>,<lon>);out center tags 80;` via POST `data=`. Ways/relations use `center`.
- `_where(near)`: same location resolution order as weather (arg → saved → IP, saved).
- Output header: `<category> near <place> (location source: ...), within <r> km. Source OpenStreetMap, no ratings.` then numbered lines.
- Empty result text: `No <category> found within <r> km of <place> in map data. Try a bigger radius.`

## 16.4 Travel: flights and other places (PLANNED v1.2.0, nothing built)

Decision log:
- Search + deep link only. No in-agent booking (Section 13 items 33, 34).
- If in-agent booking is ever added: Duffel, hard confirm showing itinerary + price + passenger, user retypes amount. Needs account and live-access onboarding; terms unverified.
- Flight search source still undecided (Section 13 item 33). Deep-link builder needs IATA codes + dates, no API.
- Places beyond nearby lookup (ratings, details) would need Google Places or Foursquare: key + billing + terms, not evaluated.

---

## 17. Roadmap / planned features (append only)

- [ ] (user to fill) planned feature 1
- [ ] (user to fill) planned feature 2
- [ ] Agent LLM call streaming (`stream=True`, assemble `tool_calls` deltas) to stop 524
- [ ] Auto-publish tunnel URLs from notebook (private gist / HF dataset), Ultron fetches on start, no manual `.env`
- [ ] Scanned PDF OCR: rasterize pages (`pypdfium2`) → same OCR endpoint → index
- [ ] OCR layout stage (PP-DocLayoutV3 / official SDK) for dense pages
- [ ] Verify and remove `[UNVERIFIED applied]` tags (agent guards, browser schema, prompt lines)
- [ ] Token-based history budget (replace char budget)
- [ ] Tool routing in `agent.py`: core tools always, group tools (browser, travel, places, weather, docs, ocr) only on keyword match or earlier use this chat. Fixes tool-count dilution (Section 13 item 30)
- [ ] After routing: one file per tool (`tools/<name>.py`: function + schema + prompt line) with auto-registry, so adding a tool is not 4 file edits
- [ ] Travel: flight search source decision, deep-link builder (`search_flights` returns options + URL), no booking
- [ ] Verify and remove `[UNVERIFIED applied]` tags: forced research, weather/location, places, `/loc`
- [ ] Tighten `RESEARCH_RE` if false positives appear
- [ ] Optional precise location via Windows Location API (needs OS permission, API not verified)
<!-- Mark done as `- [x] ... (vX.Y.Z)`, never delete items. -->

---

## 18. Quick-start prompt for pasting into any AI chat

Copy this at the top of a new chat, then paste this whole document:

> You are my engineering assistant for the project "Ultron". The attached document is the complete project context (architecture, files, tools, flow, conventions, known issues). Treat it as the source of truth. Do not assume anything not in it; ask me for specific files when needed. When we change the project, follow Section 14 and give me only the additions to append to the doc plus a Changelog row. Confirm you understood by summarizing the architecture in 5 lines and listing the 3 most serious items from Section 13. Then wait for my task.
