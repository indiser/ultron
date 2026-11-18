import asyncio
import re
import time
from contextlib import AsyncExitStack
from datetime import date

import agent
import mcp_client
from mem_tools import load_memory
from SYSTEM_PROMPT import build_prompt
from skills_tool import load_skills


async def _no_browsers(stack):
    pass


mcp_client.connect_browsers = _no_browsers  # smoke: skip heavy browser MCP

calls: list[str] = []
results: list[str] = []
_orig = agent.call_tool


async def _spy(name, args):
    calls.append(name)
    r = await _orig(name, args)
    results.append(str(r))
    return r


agent.call_tool = _spy

# (tier, prompt, must, never, rx, min_steps, order)
SCENARIOS = [
    # --- EASY (5): 0-1 step, routing + restraint ---
    ("easy", "what is 17 times 23", set(), {"web_search", "research", "get_weather"}, r"391", 0, []),
    ("easy", "how is the weather today", {"get_weather"}, {"web_search", "research"}, None, 1, []),
    ("easy", "what time is it now", {"get_current_time"}, {"web_search"}, None, 1, []),
    ("easy", "nearest pharmacy", {"find_places"}, {"web_search"}, None, 1, []),
    ("easy", "list my files", {"list_files"}, {"web_search"}, None, 1, []),

    # --- MEDIUM (5): 2 steps, dual-tool combos ---
    ("med", "check today's weather and find 3 indoor cafes near me",
     {"get_weather", "find_places"}, {"web_search"}, None, 2, []),
    ("med", "check current time and write today's timestamp to smoke_time.txt",
     {"get_current_time", "write_file"}, {"web_search"}, r"smoke_time\.txt", 2, ["get_current_time", "write_file"]),
    ("med", "list my files and save in memory how many files I currently have",
     {"list_files", "save_memory"}, set(), None, 2, ["list_files", "save_memory"]),
    ("med", "search the web for latest Python 3.13 patch version and write it to py_ver.txt",
     {"web_search", "write_file"}, {"research"}, r"3\.13\.\d+", 2, ["web_search", "write_file"]),
    ("med", "ingest https://example.com and list my files to confirm workspace state",
     {"ingest_url", "list_files"}, {"web_search"}, None, 2, ["ingest_url", "list_files"]),

    # --- HARD (5): 3 steps, multi-tool pipelines + state verification ---
    ("hard", "check current time, check today's weather, and write both into daily_brief.txt",
     {"get_current_time", "get_weather", "write_file"}, {"web_search", "research"}, r"daily_brief\.txt", 3, ["write_file"]),
    ("hard", "write 'temp data' to scratch_smoke.txt, list files to confirm it exists, then delete scratch_smoke.txt",
     {"write_file", "list_files", "delete_file"}, set(), r"scratch_smoke\.txt", 3, ["write_file", "list_files", "delete_file"]),
    ("hard", "do deep research on the history of Kolkata, write a 3-bullet summary to kolkata.md, and save a memory that kolkata.md was created",
     {"research", "write_file", "save_memory"}, {"web_search"}, r"Kolkata", 3, ["research", "write_file", "save_memory"]),
    ("hard", "find nearest hospital, search the web for India's national emergency ambulance number, and save both to emergency_info.txt",
     {"find_places", "web_search", "write_file"}, {"research"}, r"102|108|112", 3, ["write_file"]),
    ("hard", "check current time, ingest https://www.iana.org/domains/reserved, and save key takeaway in memory",
     {"get_current_time", "ingest_url", "save_memory"}, set(), None, 3, ["ingest_url", "save_memory"]),

    # --- EXTREMELY HARD (5): 4-7 steps, negative constraints, repeated calls, strict cleanup ---
    ("extreme", "without using web_search, do deep research on quantum error correction, write findings to qec_notes.txt, verify via list_files, and save a memory with the filename",
     {"research", "write_file", "list_files", "save_memory"}, {"web_search", "delete_file"}, r"qec_notes\.txt", 4, ["research", "write_file", "list_files", "save_memory"]),
    ("extreme", "check weather and current time, find 2 pharmacies near me, write an emergency checklist to temp_rx.txt, verify via list_files, then delete temp_rx.txt so workspace stays clean",
     {"get_weather", "get_current_time", "find_places", "write_file", "list_files", "delete_file"}, {"web_search"}, r"temp_rx\.txt", 6, ["write_file", "list_files", "delete_file"]),
    ("extreme", "calculate 47 * 89 without searching, check current time, write product and timestamp to calc_audit.txt, save the product to memory, then delete calc_audit.txt",
     {"get_current_time", "write_file", "save_memory", "delete_file"}, {"web_search", "research"}, r"4183", 4, ["get_current_time", "write_file", "delete_file"]),
    ("extreme", "find nearest railway station, search the web for Indian Railways helpline number, ingest https://example.com, write a combined transit note to transit.txt, and save the helpline in memory",
     {"find_places", "web_search", "ingest_url", "write_file", "save_memory"}, {"research"}, r"139", 5, ["write_file", "save_memory"]),
    ("extreme", "list my files first, create stage1.txt and stage2.txt with distinct content, list files again to confirm both exist, save their names to memory, then delete both stage1.txt and stage2.txt",
     {"list_files", "write_file", "save_memory", "delete_file"}, {"web_search", "research"}, r"stage1\.txt", 7, ["list_files", "write_file", "save_memory", "delete_file"]),
]

LEAK = re.compile(r"^\s*(the user|user input|user (is|has|asked|wants)|i (must|need to) )", re.I)
CLAIMS = {"saved": {"write_file", "research", "save_memory"}, "wrote": {"write_file"},
          "deleted": {"delete_file"}, "installed": {"install_skill", "ingest_doc", "ingest_url", "upload_doc"}}
CLAIM_PHRASE = r"\b(?:i(?:'ve| have)? |has been |have been |was ){w}\b"


def _in_order(actual: list[str], seq: list[str]) -> bool:
    it = iter(actual)
    return all(step in it for step in seq)


async def run_one(tier, prompt, must, never, rx, min_steps, order):
    calls.clear()
    results.clear()
    messages = [{"role": "system", "content": build_prompt(
        memory=load_memory(), today=date.today().isoformat(), shell="Windows cmd.exe")}]
    messages.append({"role": "user", "content": prompt})
    t = time.time()
    ans = await agent.run_agent(messages)
    fail, warn = [], []
    if not must <= set(calls):
        fail.append(f"missing tools {sorted(must - set(calls))}")
    if never & set(calls):
        fail.append(f"forbidden tools {sorted(never & set(calls))}")
    if len(calls) < min_steps:
        fail.append(f"too few steps: got {len(calls)}, expected >={min_steps}")
    if order and not _in_order(calls, order):
        fail.append(f"bad order: expected subseq {order}, got {calls}")
    if LEAK.match(ans):
        fail.append("leaked reasoning")
    if ans.startswith(("error:", "stopped:")):
        fail.append("agent error: " + ans[:80])
    if rx and not re.search(rx, ans):
        fail.append(f"answer lacks /{rx}/")
    for word, tools in CLAIMS.items():
        if re.search(CLAIM_PHRASE.format(w=word), ans, re.I) and not (tools & set(calls)):
            fail.append(f"claims '{word}' without tool")
    bad = [r[:90] for r in results if r.startswith("error:")]
    if bad and not fail:
        warn.append("tool errors (external/flaky?): " + " | ".join(bad))
    status = "FAIL" if fail else ("WARN" if warn else "PASS")
    print(f"[{tier:7s}] {status} {time.time() - t:5.1f}s  {prompt}")
    print(f"          tools={calls}  answer={ans[:110]!r}")
    for w in fail + warn:
        print("          ->", w)
    return status


async def main():
    load_skills()
    async with AsyncExitStack() as stack:
        await mcp_client.connect_mcp(stack)
        out = [await run_one(*s) for s in SCENARIOS]
    print(f"\n{out.count('PASS')} pass, {out.count('WARN')} warn, {out.count('FAIL')} fail  of {len(out)}")


asyncio.run(main())