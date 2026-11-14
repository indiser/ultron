from contextlib import AsyncExitStack
import os
from datetime import date
from mem_tools import load_memory
from SYSTEM_PROMPT import build_prompt
from agent import run_agent
from mcp_client import connect_mcp
import asyncio
import voice_out
import subprocess
import time
import socket
import shutil
from pathlib import Path
from config import WORKSPACE
from rag import ingest_doc, ingest_url, list_docs, remove_doc, upload_doc
from interrupt import run_cancellable
from text_ui import c, read_you

STOP_WORDS = {"stop", "/stop", "quiet", "enough", "shut up"}

def wait_port(port: int, timeout: float = 15) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False

async def main():
    obs = None
    try:
        obs = subprocess.Popen(["obscura", "serve"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not await asyncio.to_thread(wait_port, 9222):
            print(" [obscura] nothing on port 9222, headless browser will fail")
    except FileNotFoundError:
        print(" [obscura] obscura not in PATH, headless browser will fail")

    try:
        async with AsyncExitStack() as stack:
            await connect_mcp(stack)
            messages = [
                {"role": "system", "content": build_prompt(
                    memory=load_memory(),
                    today=date.today().isoformat(),
                    shell="Windows cmd.exe" if os.name == "nt" else "bash")}
            ]
            # print("\nUltron")
            print(c("info", "\nUltron"))
            pending = []
            try:
                while True:
                    # user = input("\nyou: ")
                    user = read_you()
                    cmd = user.strip()
                    if cmd.lower().strip(" .!") in STOP_WORDS:
                        voice_out.stop()
                        continue
                    if cmd == "/upload":
                        res = await asyncio.to_thread(upload_doc)
                        print(res)
                        for line in res.splitlines():
                            if line.startswith("indexed:"):
                                pending.append(line)
                        continue
                    if cmd.startswith("/add "):
                        arg = cmd[5:].strip().strip('"')
                        if arg.startswith("http"):
                            res = await ingest_url(arg)
                        else:
                            src = Path(arg)
                            if not src.is_file():
                                print("no such file")
                                continue
                            shutil.copy(src, WORKSPACE / src.name)
                            res = await asyncio.to_thread(ingest_doc, src.name)
                        print(res)
                        if res.startswith("indexed:"):
                            pending.append(res)
                        continue
                    if cmd == "/docs":
                        print(list_docs())
                        continue
                    if cmd.startswith("/remove "):
                        print(remove_doc(cmd[8:].strip()))
                        continue
                    held = list(pending)
                    if pending:
                        user = "[system: " + "; ".join(pending) + ". Use search_docs or read_doc for questions about them.]\n" + user
                        pending.clear()
                    voice_out.stop()
                    n = len(messages)
                    messages.append({"role": "user", "content": user})
                    # print(" [Esc = cancel]")
                    print(c("think", " [Esc = cancel]"))
                    answer, cancelled = await run_cancellable(run_agent(messages))
                    if cancelled:
                        del messages[n:]
                        pending.extend(held)
                        voice_out.stop()
                        # print("\n [cancelled]")
                        print(c("info", "\n [cancelled]"))
                        continue
                    # answer = await run_agent(messages)
                    # print(f"\nAssistant: {answer}")
                    # if not answer.startswith("error:"):
                    #     voice_out.speak(answer)
                    if answer.startswith("error:"):
                        print("\n" + c("error", answer))
                    else:
                        print("\n" + c("assistant", "Assistant: " + answer))
                        voice_out.speak(answer)
                    # voice_out.speak(answer)
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
    finally:
        if obs:
            obs.terminate()


if __name__ == "__main__":
    asyncio.run(main())