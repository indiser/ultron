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

def set_browser_mode(mode: str) -> str:
    if mode not in ("headless", "visible"):
        return "error: mode must be headless or visible"
    if mode not in browser_sessions:
        return f"error: {mode} browser not connected"
    browser_state["mode"] = mode
    return f"browser mode: {mode}. Page state not carried over. Call browser_navigate again."

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
}

GATED = {"browser_click", "browser_type", "browser_fill_form", "browser_press_key", "remove_doc", "delete_file"}

# Call tools mcp or local as nesessary
async def call_tool(name: str, args: dict) -> str:
    if name in GATED:
        if ask(f"\n Confirm {name} {args}? [y/N] ").strip().lower() != "y":
            return "The user declined this action"
    if name == "research":
        return await research(**args)
    if name == "ingest_url":
        return await ingest_url(**args)
    if name == "ocr_image":
        return await ocr_image(**args)
    if name in LOCAL_TOOLS:
        return LOCAL_TOOLS[name](**args)
    if name == "get_weather":
        return await get_weather(**args)
    if name == "use_skill":
        return await use_skill(**args)
    if name == "find_places":
        return await find_places(**args)
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
    result = await mcp_session[name].call_tool(name, args)
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))[:5000]

def missing_args(name: str, args: dict) -> list[str]:
    for t in TOOL_SCHEMAS:
        f = t["function"]
        if f["name"] == name:
            return [k for k in f["parameters"].get("required", []) if args.get(k) in (None, "")]
    return []