from contextlib import AsyncExitStack
import os
from datetime import date
from mem_tools import load_memory
from SYSTEM_PROMPT import SYSTEM_PROMPT
from agent import run_agent
from mcp_client import connect_mcp
import asyncio
import voice_out

async def main():
    async with AsyncExitStack() as stack:
        await connect_mcp(stack)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(
                memory=load_memory(), today=date.today().isoformat(),
                shell="Windows cmd.exe" if os.name == "nt" else "bash")}
        ]
        print("\nOffline Code")
        try:
            while True:
                user = input("\nyou: ")
                voice_out.stop()
                messages.append({"role": "user", "content": user})
                answer = await run_agent(messages)
                print(f"\nAssistant: {answer}")
                voice_out.speak(answer)
        except (EOFError, KeyboardInterrupt):
            print("\nbye")


if __name__ == "__main__":
    asyncio.run(main())