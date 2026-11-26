from file_tools import *
from mem_tools import *
from shell_tool import *
from web_tool import *
from mcp_client import mcp_session, browser_sessions, browser_state
from research_tool import research
from tools_schema import TOOL_SCHEMAS
from rag import ingest_doc, search_docs, read_doc, list_docs, upload_doc, ingest_url, remove_doc
from interrupt import ask
from ocr_tool import ocr_image
from weather_tool import get_weather
from places_tool import find_places
from skills_tool import use_skill
from skills_install import install_skill
from calc_tool import *
from status_tool import *
from recall_tool import recall
import asyncio
from github_tool import github
from currency_tool import *
from scheduler_tool import *
from air_sun_tool import air_quality, sun_times
from youtube_tool import youtube_transcript
from telegram_tool import send_telegram, read_telegram
from repo_tool import repo
from text_ui import SOURCE
from export_tool import export_doc
from astro_dispatch import BIRTH_TOOLS, collect_birth_details, run_birth_tool
import re
import json

def set_browser_mode(mode: str) -> str:
    if mode not in ("headless", "visible"):
        return "error: mode must be headless or visible"
    if mode not in browser_sessions:
        return f"error: {mode} browser not connected"
    browser_state["mode"] = mode
    return f"browser mode: {mode}. Page state not carried over. Call browser_navigate again."

async def download_paper_full(paper_id: str) -> str:
    parts, start = [], 0
    for _ in range(12):
        r = await mcp_session["download_paper"].call_tool(
            "download_paper", {"paper_id": paper_id, "start": start})
        raw = "\n".join(c.text for c in r.content if hasattr(c, "text"))
        try:
            d = json.loads(raw)
        except ValueError:
            return f"error: bad response: {raw[:200]}"
        if d.get("status") != "success":
            return f"error: {raw[:300]}"
        parts.append(d.get("content", ""))
        if not d.get("is_truncated"):
            break
        start = d["next_start"]
    text = "".join(parts)
    if not text.strip():
        return "error: empty paper text"
    name = f"arxiv_{paper_id.replace('/', '_')}.md"
    LOCAL_TOOLS["write_file"](filename=name, contents=text)
    return LOCAL_TOOLS["ingest_doc"](filename=name)

EXAMPLES = {
    "resolve-library-id": '{"libraryName": "pydantic", "query": "model_validator mode after"}',
    "query-docs": '{"libraryId": "/pydantic/pydantic", "query": "model_validator mode after"}',
    "download_paper": '{"paper_id": "2106.09685"}',
    "search_papers": '{"query": "speculative decoding", "max_results": 5}',
}

DOCS_RE = re.compile(r"\b(docs?|documentation|api|sdk|framework|library|package)\b", re.I)
ctx7_state = {"used": False}
ARXIV_RE = re.compile(r"\b(arxiv|papers?|preprints?)\b", re.I)
arxiv_state = {"used": False}

# Local initialised tools
LOCAL_TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "delete_file": delete_file,
    "save_memory": save_memory,
    "run_command": run_command,
    "edit_file": edit_file,
    "web_search": web_search,
    "set_browser_mode": set_browser_mode,
    "ingest_doc": ingest_doc,
    "search_docs": search_docs,
    "read_doc": read_doc,
    "list_docs": list_docs,
    "upload_doc": upload_doc,
    "remove_doc": remove_doc,
    "calculate": calculate,
    "system_status": system_status,
    "read_telegram": read_telegram,
}

GATED = {"browser_click", "browser_type", "browser_fill_form", "browser_press_key", "remove_doc", "delete_file", "export_doc"}

# Call tools mcp or local as nesessary
async def call_tool(name: str, args: dict) -> str:
    if name in GATED:
        if SOURCE.get() == "tg":
            return "The user declined: this needs confirmation at the PC."
        if ask(f"\n Confirm {name} {args}? [y/N] ").strip().lower() != "y":
            return "The user declined this action"
    if name == "resolve-library-id":
        ctx7_state["used"] = True
    if name in ("web_search", "research") and not ctx7_state["used"] \
            and DOCS_RE.search(args.get("query", "")):
        return "error: library docs need resolve-library-id then query-docs. Call resolve-library-id first."
    if name == "search_papers":
        arxiv_state["used"] = True
    if name in ("web_search", "research") and not arxiv_state["used"] \
            and ARXIV_RE.search(args.get("query", "")):
        return "error: papers need search_papers first. Call search_papers."
    if name == "research":
        return await research(**args)
    if name == "ingest_url":
        return await ingest_url(**args)
    if name == "ocr_image":
        return await ocr_image(**args)
    if name == "collect_birth_details":
        if SOURCE.get() == "tg":
            return "error: birth form opens on the PC. Ask the user to use the terminal."
        return await collect_birth_details()
    if name in BIRTH_TOOLS:
        return await run_birth_tool(name, args)
    if name in LOCAL_TOOLS:
        return LOCAL_TOOLS[name](**args)
    if name == "download_paper":
        return await download_paper_full(**args)
    if name == "get_weather":
        return await get_weather(**args)
    if name == "youtube_transcript":
        return await youtube_transcript(**args)
    if name == "use_skill":
        return await use_skill(**args)
    if name == "export_doc":
        return await export_doc(**args)
    if name == "send_telegram":
        return await send_telegram(**args)
    if name == "find_places":
        return await find_places(**args)
    if name == "air_quality":
        return await air_quality(**args)
    if name == "sun_times":
        return await sun_times(**args)
    if name == "repo" and args.get("action") in ("clone", "setup", "run", "remove"):
        if SOURCE.get() == "tg":
            return "The user declined: this needs confirmation at the PC."
        if ask(f"\n Confirm repo {args}? [y/N] ").strip().lower() != "y":
            return "The user declined this action"
    if name == "repo":
        return await repo(**args)
    if name == "convert_currency":
        return await convert_currency(
            amount=args.get("amount", 1),
            from_currency=args.get("from_currency", ""),
            to_currency=args.get("to_currency", ""),
            date=args.get("date", ""),
        )
    if name == "manage_schedule":
        return await manage_schedule(
            action=args.get("action", ""),
            name=args.get("name", ""),
            when=args.get("when", ""),
            cron=args.get("cron", ""),
            task=args.get("task", ""),
            mode=args.get("mode", "notify"),
            job_id=args.get("job_id", ""),
        )
    if name == "recall":
        return await asyncio.to_thread(recall, args.get("query", ""), args.get("days_back"))
    if name == "github":
        return await github(**args)
    if name == "install_skill":
        return await install_skill(**args)
    if name == "browser_navigate" and not args.get("url"):
        return 'error: browser_navigate needs url. Resend exactly: {"url": "https://en.wikipedia.org/wiki/India"} with the real link.'
    if name.startswith("browser_"):
        s = browser_sessions.get(browser_state["mode"])
        if not s:
            return f"error: {browser_state['mode']} browser not connected"
        result = await s.call_tool(name, args)
        return "\n".join(c.text for c in result.content if hasattr(c, "text"))[:8000]
    miss = missing_args(name, args)
    if miss:
        return f"error: missing {miss}. Resend with real values, e.g. {EXAMPLES.get(name, '')}"
    result = await mcp_session[name].call_tool(name, args)
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))[:5000]

def missing_args(name: str, args: dict) -> list[str]:
    for t in TOOL_SCHEMAS:
        f = t["function"]
        if f["name"] == name:
            return [k for k in f["parameters"].get("required", []) if args.get(k) in (None, "")]
    return []