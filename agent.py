import asyncio
import time
from types import SimpleNamespace
from config import client, MODEL
from tools_schema import TOOL_SCHEMAS
import json
from tools import call_tool, missing_args
import traceback
from text_ui import c, SOURCE
import re
from skills_tool import ACTIVE, LIST_MARK, SKILL_MARK, active_block, route, skills_block
from skills_install import source_in_text

RESEARCH_RE = re.compile(r"\b(?:deep[- ]research|research(?:ing)?\s+(?:on|about|into|this|it|the|how|why|what|who|when|where)|(?:do|run|please|can you)\s+research)\b|^\s*research\b", re.I)
NUDGE = "[nudge] "
FILE_RE = re.compile(r"\b(?:write|create|file|csv|txt|download|export)\b|\.(?:txt|csv|md)\b|\bsave\s+(?:to|as|in)\s+(?!memory\b)", re.I)
LEAK_RE = re.compile(r"^\s*(?:the user|user input|user (?:is|has|asked|wants|repeated)|i (?:must|need to|will) )", re.I)

REQUIRED = [
    (re.compile(r"\b(?:weather|forecast|will it rain|is it raining|how (?:hot|cold)|temperature (?:today|now|outside))\b", re.I), "get_weather"),
    (re.compile(r"\b(?:near me|nearby|around me|closest|nearest)\b", re.I), "find_places"),
]
CLAIM_RE = re.compile(r"\b(?:i(?:'ve| have)? |has been |have been |was )(?:checked|saved|written|wrote|deleted|installed|searched|looked up)\b", re.I)
LIST_RE = re.compile(r"\b(?:top|best|largest|biggest|ranked|ranking|timeline|list of)\b|\b\d+\s+(?:items|rows|cities|countries|companies)\b", re.I)
CLEANUP_RE = re.compile(r"\b(?:delete|remove|clean\s*up)\b", re.I)
CANNED_RE = re.compile(r"^\s*done\.|you're welcome\.\s*again", re.I)
TARGET_FILE_RE = re.compile(r"\b([\w-]+\.(?:txt|md|csv|py|json))\b", re.I)
MATH_RE = re.compile(r"\b(\d+)\s*(?:\*|x|times)\s*(\d+)\b", re.I)
MEM_RE = re.compile(r"\b(?:save|store|record|keep)\b.*\bmemory\b|\bremember\b", re.I)
VERIFY_LIST_RE = re.compile(r"\b(?:verify|confirm|check)\b.*\blist_files\b|\blist\s+files\s+(?:again|to\s+confirm|to\s+verify)\b", re.I)
SUMMARY_REQ_RE = re.compile(r"\b(?:summary|summarize|findings|takeaway|brief)\b", re.I)
LAZY_FILE_REPLY_RE = re.compile(r"\b(?:summary|findings|note|brief|checklist)\s+(?:is|are|has been|was)\s+(?:in|saved|written)\b", re.I)

def last_user(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            t = m.get("content") or ""
            if t.startswith("[system:"):
                t = t.split("\n", 1)[-1]
            return t
    return ""

def tg() -> str:
    return "[tg] " if SOURCE.get() == "tg" else ""

def purge_nudges(messages: list) -> None:
    messages[:] = [m for m in messages
                   if not (isinstance(m, dict) and str(m.get("content") or "").startswith(NUDGE))]

MAX_STEPS = 40
RESULT_CAP = 8000

def budget(messages: list, extra: int = 12000) -> int:
    return len(str(messages[0])) + extra

def trim_history(messages: list, max_chars: int | None = None) -> None:
    max_chars = max_chars or budget(messages)
    if sum(len(str(m)) for m in messages) <= max_chars:
        return
    tool_idx = [i for i, m in enumerate(messages)
                if isinstance(m, dict) and m.get("role") == "tool"]
    for i in tool_idx[:-2]:
        old = messages[i]["content"]
        if len(old) > 300:
            messages[i]["content"] = old[:300] + " [old result trimmed]"

def drop_old_turns(messages: list, max_chars: int | None = None) -> None:
    max_chars = max_chars or budget(messages)
    while sum(len(str(m)) for m in messages) > max_chars:
        user_idx = [i for i, m in enumerate(messages)
                    if isinstance(m, dict) and m.get("role") == "user"]
        if len(user_idx) < 3:
            return
        del messages[user_idx[0]:user_idx[1]]

def trace(event: str, **kw) -> None:
    try:
        with open("trace.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 1), "event": event, **kw}, default=str)[:3000] + "\n")
    except OSError:
        pass

def _safe_args(raw: str | None) -> str:
    s = raw or "{}"
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        return "{}"

async def chat_stream(messages: list) -> SimpleNamespace:
    stream = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOL_SCHEMAS,
        temperature=0.1,
        max_tokens=8192,
        stream=True,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    text, slots = [], {}
    async for chunk in stream:
        if not chunk.choices:
            continue
        d = chunk.choices[0].delta
        if d.content:
            text.append(d.content)
        for tc in d.tool_calls or []:
            slot = slots.setdefault(tc.index, {"id": "", "name": "", "args": ""})
            if tc.id and not slot["id"]:
                slot["id"] = tc.id
            if tc.function:
                if tc.function.name and not slot["name"]:
                    slot["name"] = tc.function.name
                if tc.function.arguments:
                    slot["args"] += tc.function.arguments
    calls = [SimpleNamespace(id=v["id"] or f"call_{i}",
                             function=SimpleNamespace(name=v["name"], arguments=v["args"]))
             for i, v in sorted(slots.items())]
    return SimpleNamespace(content="".join(text), tool_calls=calls)


# Agent harness loop
async def run_agent(messages: list) -> str:
    nudged = False
    searched = False
    seen = set()
    purge_nudges(messages)
    user_text = last_user(messages)
    base = messages[0]["content"].split(LIST_MARK)[0].split(SKILL_MARK)[0]
    ACTIVE["name"] = await asyncio.to_thread(route, user_text)
    want_research = bool(RESEARCH_RE.search(user_text))
    want_file = bool(FILE_RE.search(user_text))
    researched = False
    r_nudged = False
    fails = {}
    cmd_fails = 0
    errs = 0
    leak_nudged = False
    used = set()
    req_nudged = set()
    claim_nudged = False
    for _ in range(MAX_STEPS):
        messages[0]["content"] = base + skills_block() + active_block()
        trim_history(messages=messages)
        drop_old_turns(messages=messages)
        t = time.time()
        try:
            message = await chat_stream(messages)
        except Exception as e:
            body = getattr(getattr(e, "response", None), "text", "")
            trace("final", text=f"model call failed: {e}"[:400])
            return f"error: model call failed: {e} {body[:800]}"

        # print(c("think", f" [llm] {time.time() - t:.1f}s"))
        print(c("think", f" {tg()}[llm] {time.time() - t:.1f}s"))
    
        if not message.tool_calls:
            text = message.content or ""
            if want_research and not researched and not r_nudged:
                r_nudged = True
                trace("guard", kind="research_nudge")
                if text.strip():
                    messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": NUDGE + f"Research request: {user_text[:300]}. Call the research tool now with a query taken from that request. Do not answer from memory."})
                continue
            need = next((t for rx, t in REQUIRED
                         if rx.search(user_text) and t not in used and t not in req_nudged
                         and any(x["function"]["name"] == t for x in TOOL_SCHEMAS)), None)
            if need:
                req_nudged.add(need)
                trace("guard", kind=f"required_{need}")
                messages.append({"role": "user", "content": NUDGE + f"Call the {need} tool now for the user's request. Do not answer from memory."})
                continue
            if not used and CLAIM_RE.search(text) and not claim_nudged:
                claim_nudged = True
                trace("guard", kind="claim_without_tool")
                messages.append({"role": "user", "content": NUDGE + "You described an action but no tool ran. Say plainly what you did not do, or call the right tool."})
                continue
            if CLEANUP_RE.search(user_text) and "write_file" in used and "delete_file" not in used and "cleanup" not in req_nudged:
                req_nudged.add("cleanup")
                trace("guard", kind="missing_cleanup")
                messages.append({"role": "user", "content": NUDGE + "You created a temporary file with write_file but did not call delete_file yet. Delete it now before answering."})
                continue
            if VERIFY_LIST_RE.search(user_text) and "write_file" in used and "list_files" not in used and "verify_list" not in req_nudged:
                req_nudged.add("verify_list")
                trace("guard", kind="missing_verify_list")
                messages.append({"role": "user", "content": NUDGE + "Call list_files now to verify the file you just wrote before answering."})
                continue
            if MEM_RE.search(user_text) and "save_memory" not in used and "memory" not in req_nudged:
                req_nudged.add("memory")
                trace("guard", kind="missing_save_memory")
                messages.append({"role": "user", "content": NUDGE + "You have not saved to memory yet. Call save_memory now before answering."})
                continue
            if want_file and "write_file" not in used and not any(
                m.get("role") == "tool" and str(m.get("content", "")).startswith("DONE.")
                for m in messages
            ) and "write" not in req_nudged:
                req_nudged.add("write")
                trace("guard", kind="missing_write_file")
                messages.append({"role": "user", "content": NUDGE + "You have not written the requested file yet. Call write_file now with the gathered content before answering."})
                continue
            target_files = TARGET_FILE_RE.findall(user_text)
            if target_files and any(f not in text for f in target_files) and "filename" not in req_nudged:
                req_nudged.add("filename")
                trace("guard", kind="missing_filename")
                messages.append({"role": "user", "content": NUDGE + f"Include the exact filename(s) {', '.join(target_files)} and key results in your final reply."})
                continue
            if SUMMARY_REQ_RE.search(user_text) and "write_file" in used and LAZY_FILE_REPLY_RE.search(text) and "summary_body" not in req_nudged:
                req_nudged.add("summary_body")
                trace("guard", kind="missing_summary_body")
                messages.append({"role": "user", "content": NUDGE + "Include the actual summary or key findings directly in your reply, not just a pointer to the file."})
                continue
            if (mm := MATH_RE.search(user_text)) and "math" not in req_nudged:
                expected = str(int(mm.group(1)) * int(mm.group(2)))
                if expected not in text:
                    req_nudged.add("math")
                    trace("guard", kind="wrong_math")
                    messages.append({"role": "user", "content": NUDGE + f"Arithmetic error in your reply. Re-check {mm.group(1)} * {mm.group(2)} carefully and state the exact number."})
                    continue
            if used and CANNED_RE.match(text) and "canned" not in req_nudged:
                req_nudged.add("canned")
                trace("guard", kind="canned_reply")
                messages.append({"role": "user", "content": NUDGE + "Do not reply with generic 'Done.' filler. State the exact filenames, numbers, or facts returned by the tools."})
                continue
            if LEAK_RE.match(text) and not leak_nudged:
                leak_nudged = True
                trace("guard", kind="leak_nudge")
                messages.append({"role": "user", "content": NUDGE + "Your reply contained your own reasoning. Reply again with only the answer for the user. No analysis."})
                continue
            if not text.strip() and not nudged:
                nudged = True
                trace("guard", kind="empty_nudge")
                messages.append({"role": "user", "content": NUDGE + "Answer now, briefly, from the tool results above."})
                continue
            if not text.strip():
                text = "(model returned an empty reply)"
            messages.append({"role": "assistant", "content": text})
            trace("final", text=text[:400])
            return text
    
        # messages.append({"role": "assistant", "content": message.content or "",
        #                  "tool_calls": [{"id": tc.id, "type": "function",
        #                                  "function": {"name": tc.function.name,
        #                                               "arguments": tc.function.arguments or "{}"}}
        #                                 for tc in message.tool_calls]})
        messages.append({"role": "assistant", "content": message.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name,
                                                      "arguments": _safe_args(tc.function.arguments)}}
                                        for tc in message.tool_calls]})
    
        for call in message.tool_calls:
            name = call.function.name
            args = {}
            try:
                args = json.loads(call.function.arguments or "{}")
                if want_research and name == "web_search":
                    name = "research"
                    args = {"query": args.get("query", "")}
                # if name == "research":
                #     researched = True
                #     if args.get("save_to") and not want_file:
                #         args.pop("save_to")
                if name == "research":
                    researched = True
                    st = args.get("save_to", "")
                    if st and not (st.lower().endswith(".csv") or LIST_RE.search(user_text)):
                        args.pop("save_to")
                used.add(name)
                # print(c("tool", f" [tool] {name}({args})"))
                print(c("tool", f" {tg()}[tool] {name}({args})"))
                key = (name, json.dumps(args, sort_keys=True))
                if name == "research" and not searched and not args.get("save_to") and not want_research:
                    result = "error: call web_search first. Use research only if snippets lack the answer."
                elif name == "run_command" and cmd_fails >= 5:
                    result = "error: 5 commands failed. Stop. Tell the user what failed and what you tried."
                elif name == "install_skill" and not source_in_text(args.get("source", ""), user_text):
                    result = "error: install_skill only works for a source the user typed. Ask the user for the skill link."
                elif name == "save_memory" and not MEM_RE.search(user_text):
                    result = "error: save_memory only when the user asks to remember something. Skip it."
                elif fails.get(key, 0) >= 2:
                    result = "error: this exact call failed twice. Change the args or tell the user what is missing."
                elif key in seen and name not in ("run_command", "browser_snapshot", "set_browser_mode"):
                    result = "error: identical call already made. Change the query or approach, or answer now."
                elif (miss := missing_args(name, args)):
                    result = f"error: {name} missing required args: {', '.join(miss)}. Resend the full call with all args."
                elif name == "save_memory" and want_file and "write_file" not in used and not any(
                    m.get("role") == "tool" and str(m.get("content", "")).startswith("DONE.")
                    for m in messages
                ):
                    result = "error: write the file with write_file first before calling save_memory."
                else:
                    seen.add(key)
                    if name in ("web_search", "research"):
                        searched = True
                    result = str(await call_tool(name, args))[:RESULT_CAP]
                    if result.startswith("error:"):
                        seen.discard(key)
                        fails[key] = fails.get(key, 0) + 1
                    else:
                        used.add(name)
                    if name in ("write_file", "edit_file", "delete_file") and result.startswith(("wrote", "edited", "deleted")):
                        seen.clear()
                    if name == "write_file" and result.startswith("wrote"):
                        cmd_fails = 0
                    if name == "run_command" and any(s in result for s in ("is not recognized", "SyntaxError", "Traceback", "was unexpected")):
                        cmd_fails += 1
                # print(c("result", f" [result] {result[:300]}"))
                print(c("result", f" {tg()}[result] {result[:300]}"))
            except json.JSONDecodeError as e:
                result = f"error: JSONDecodeError ({e}). Tool arguments were truncated. Write smaller files (<100 lines) or build incrementally with write_file + edit_file."
                print(c("error", f" [error] {result}"))
            except Exception as e:
                traceback.print_exc()
                result = f"error: {type(e).__name__}: {e}"
                print(c("error", f" [error] {result}"))
            trace("tool", name=name, args=args, result=result[:400])
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            errs = errs + 1 if result.startswith("error:") else 0
        if errs >= 4:
            text = "stopped: tools kept failing. Last error: " + result[:200]
            trace("final", text=text)
            messages.append({"role": "assistant", "content": text})
            return text
    trace("final", text="stopped: too many tool steps")
    return "stopped: too many tool steps. Ask again with a narrower request."