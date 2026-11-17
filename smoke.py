import asyncio
import re
import time
from datetime import date

import agent
from SYSTEM_PROMPT import build_prompt
from mem_tools import load_memory

calls: list[str] = []
_orig = agent.call_tool

from skills_tool import load_skills
load_skills()

async def _spy(name, args):
    calls.append(name)
    return await _orig(name, args)


agent.call_tool = _spy

# (prompt, tools that MUST be called, tools that MUST NOT be called, regex answer must match or None)
SCENARIOS = [
    ("what is 17 times 23", set(), {"web_search", "research"}, r"391"),
    ("how is the weather today", {"get_weather"}, {"web_search"}, None),
    ("nearest pharmacy", {"find_places"}, {"web_search"}, None),
    ("what are some interesting places near me", {"find_places"}, set(), None),
    ("list my files", {"list_files"}, set(), None),
    ("deep research on the history of Kolkata, short summary", {"research"}, {"web_search"}, None),
]
LEAK = re.compile(r"^\s*(the user|user input|user (is|has|asked|wants)|i (must|need to) )", re.I)
CLAIMS = {"saved": {"write_file", "research", "save_memory"}, "wrote": {"write_file"},
          "deleted": {"delete_file"}, "installed": {"install_skill", "ingest_doc", "ingest_url", "upload_doc"}}


async def run_one(prompt, must, never, rx):
    calls.clear()
    messages = [{"role": "system", "content": build_prompt(
        memory=load_memory(), today=date.today().isoformat(), shell="Windows cmd.exe")}]
    messages.append({"role": "user", "content": prompt})
    t = time.time()
    ans = await agent.run_agent(messages)
    why = []
    if not must <= set(calls):
        why.append(f"missing tools {sorted(must - set(calls))}")
    if never & set(calls):
        why.append(f"forbidden tools {sorted(never & set(calls))}")
    if LEAK.match(ans):
        why.append("leaked reasoning")
    if ans.startswith(("error:", "stopped:")):
        why.append("agent error: " + ans[:80])
    if rx and not re.search(rx, ans):
        why.append(f"answer lacks /{rx}/")
    for word, tools in CLAIMS.items():
        if re.search(rf"\b{word}\b", ans, re.I) and not (tools & set(calls)):
            why.append(f"claims '{word}' without tool")
    print(f"{'PASS' if not why else 'FAIL'} {time.time() - t:5.1f}s  {prompt}")
    print(f"      tools={calls}  answer={ans[:110]!r}")
    for w in why:
        print("      ->", w)
    return not why


async def main():
    ok = [await run_one(*s) for s in SCENARIOS]
    print(f"\n{sum(ok)}/{len(ok)} passed")


asyncio.run(main())