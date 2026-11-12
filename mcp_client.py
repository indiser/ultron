from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools_schema import TOOL_SCHEMAS
import os

NPX = "npx.cmd" if os.name == "nt" else "npx"

BROWSER_SERVERS = {
    "headless": StdioServerParameters(
        command=NPX,
        args=["@playwright/mcp@latest", "--cdp-endpoint", "ws://127.0.0.1:9222/devtools/browser"]),
    "visible": StdioServerParameters(
        command=NPX,
        args=["@playwright/mcp@latest", "--isolated"]),
}
browser_sessions: dict[str, ClientSession] = {}
browser_state = {"mode": "headless"}

MCP_SERVERS = {
    "time": StdioServerParameters(command="uvx", args = ["mcp-server-time"]),
    "scrapling": StdioServerParameters(command="scrapling", args=["mcp"])
}

mcp_session: dict[str, ClientSession] = {}

ALLOWED = {"get_current_time", "make_request"}
HIDDEN_TOOLS = {"make_request"}
BROWSER_ALLOWED = {"browser_navigate", "browser_snapshot", "browser_click",
                   "browser_type", "browser_fill_form", "browser_press_key",
                   "browser_wait_for"}

async def connect_browsers(stack: AsyncExitStack):
    registered = False
    for mode, params in BROWSER_SERVERS.items():
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = (await session.list_tools()).tools
        except Exception as e:
            print(f" [mcp] FAILED: browser {mode}: {type(e).__name__}: {e}")
            continue
        # print(f" [mcp] browser {mode} offers: {[t.name for t in tools]}")
        browser_sessions[mode] = session
        if registered:
            continue
        for tool in tools:
            if tool.name not in BROWSER_ALLOWED:
                continue
            schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
            TOOL_SCHEMAS.append({"type": "function", "function": {
                "name": tool.name, "description": tool.description or "", "parameters": schema}})
        registered = True
        print(f" [mcp] browser tools registered: {[t.name for t in tools if t.name in BROWSER_ALLOWED]}")


# Make connection to MCP servers that are allowed
async def connect_mcp(stack: AsyncExitStack):
    for name, params in MCP_SERVERS.items():
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = (await session.list_tools()).tools
            # print(f" [mcp] {name} offers: {[t.name for t in tools]}")
        except Exception as e:
            print(f" [mcp] FAILED: {name}: {type(e).__name__}: {e}")
            continue

        loaded = []
        for tool in tools:
            if tool.name not in ALLOWED:
                continue
            mcp_session[tool.name] = session
            loaded.append(tool.name)
            if tool.name in HIDDEN_TOOLS:
                continue
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "inputSchema", None) \
                or {"type": "object", "properties": {}}
            TOOL_SCHEMAS.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": schema,
                    },
                }
            )
        print(f" [mcp] connected: {name}: {loaded}")
    await connect_browsers(stack)