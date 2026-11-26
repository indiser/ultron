import asyncio
import json

from birth_form import collect_birth
from mcp_client import mcp_session

BIRTH_TOOLS = {"get_birth_chart", "get_dasha", "get_transits", "get_horoscope"}
BIRTH_KEYS = {"date", "time", "lat", "lon", "tz"}

birth_state: dict | None = None


async def collect_birth_details() -> str:
    global birth_state
    b = await asyncio.to_thread(collect_birth)
    if b is None:
        return json.dumps({"error": "user did not submit the form in time."})
    birth_state = b
    return json.dumps({"ok": True, "place": b["place"],
                       "date": b["date"], "time": b["time"]})


async def run_birth_tool(name: str, args: dict) -> str:
    if not birth_state:
        return json.dumps({"error": "no birth details yet. call collect_birth_details first."})
    session = mcp_session.get(name)
    if session is None:
        return json.dumps({"error": "astrology server not connected."})
    args = {**args, **{k: v for k, v in birth_state.items() if k in BIRTH_KEYS}}
    r = await session.call_tool(name, args)
    text = "\n".join(c.text for c in r.content if hasattr(c, "text"))
    failed = getattr(r, "is_error", False) or getattr(r, "isError", False)
    return json.dumps({"error": text}) if failed else text