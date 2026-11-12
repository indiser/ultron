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
            print("\nUltron")
            pending = []
            try:
                while True:
                    user = input("\nyou: ")
                    cmd = user.strip()
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
                    if pending:
                        user = "[system: " + "; ".join(pending) + ". Use search_docs or read_doc for questions about them.]\n" + user
                        pending.clear()
                    voice_out.stop()
                    messages.append({"role": "user", "content": user})
                    answer = await run_agent(messages)
                    print(f"\nAssistant: {answer}")
                    voice_out.speak(answer)
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
    finally:
        if obs:
            obs.terminate()


if __name__ == "__main__":
    asyncio.run(main())