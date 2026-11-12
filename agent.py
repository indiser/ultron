import time
from config import client, MODEL
from tools_schema import TOOL_SCHEMAS
import json
from tools import call_tool, missing_args
import traceback


MAX_STEPS = 40
RESULT_CAP = 8000

def budget(messages: list, extra: int = 32000) -> int:
    return len(str(messages[0])) + extra

def trim_history(messages: list, max_chars: int | None = None) -> None:
    max_chars = max_chars or budget(messages)
    if sum(len(str(m)) for m in messages) <= max_chars:
        return
    tool_idx = [i for i, m in enumerate(messages)
                if isinstance(m, dict) and m.get("role") == "tool"]
    for i in tool_idx[:-2]:
        c = messages[i]["content"]
        if len(c) > 300:
            messages[i]["content"] = c[:300] + " [old result trimmed]"

def drop_old_turns(messages: list, max_chars: int | None = None) -> None:
    max_chars = max_chars or budget(messages)
    while sum(len(str(m)) for m in messages) > max_chars:
        user_idx = [i for i, m in enumerate(messages)
                    if isinstance(m, dict) and m.get("role") == "user"]
        if len(user_idx) < 3:
            return
        del messages[user_idx[0]:user_idx[1]]

# Agent harness loop
async def run_agent(messages: list) -> str:
    nudged = False
    searched = False
    seen = set()
    cmd_fails = 0
    for _ in range(MAX_STEPS):
        trim_history(messages=messages)
        drop_old_turns(messages=messages)
        t = time.time()
        try:
            response = await client.chat.completions.create(
                model= MODEL,
                messages= messages,
                tools= TOOL_SCHEMAS,
                temperature= 0.1,
                reasoning_effort = "medium"
            )
        except Exception as e:
            body = getattr(getattr(e, "response", None), "text", "")
            return f"error: model call failed: {e} {body[:800]}"
    
        print(f" [llm] {time.time() - t:.1f}s")
        message = response.choices[0].message
    
        if not message.tool_calls:
            text = message.content or ""
            if not text.strip() and not nudged:
                nudged = True
                messages.append({"role": "user", "content": "Answer now, briefly, from the tool results above."})
                continue
            if not text.strip():
                text = "(model returned an empty reply)"
            messages.append({"role": "assistant", "content": text})
            return text
    
        messages.append(message)
    
        for call in message.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                print(f" [tool] {name}({args})")
                key = (name, json.dumps(args, sort_keys=True))
                if name == "research" and not searched and not args.get("save_to"):
                    result = "error: call web_search first. Use research only if snippets lack the answer."
                elif name == "run_command" and cmd_fails >= 5:
                    result = "error: 5 commands failed. Stop. Tell the user what failed and what you tried."
                elif key in seen and name not in ("run_command", "browser_snapshot", "set_browser_mode"):
                    result = "error: identical call already made. Change the query or approach, or answer now."
                elif (miss := missing_args(name, args)):
                    result = f"error: {name} missing required args: {', '.join(miss)}. Resend the full call with all args."
                else:
                    seen.add(key)
                    if name == "web_search":
                        searched = True
                    result = str(await call_tool(name, args))[:RESULT_CAP]
                    if name == "write_file" and result.startswith("wrote"):
                        cmd_fails = 0
                    if name == "run_command" and any(s in result for s in ("is not recognized", "SyntaxError", "Traceback", "was unexpected")):
                        cmd_fails += 1
                print(f" [result] {result[:300]}")
            except Exception as e:
                traceback.print_exc()
                result = f"error: {type(e).__name__}: {e}"
                print(f" [error] {result}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "stopped: too many tool steps. Ask again with a narrower request."