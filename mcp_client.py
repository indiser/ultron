from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools_schema import TOOL_SCHEMAS

MCP_SERVERS = {
    "time": StdioServerParameters(command="uvx", args = ["mcp-server-time"]),
    "scrapling": StdioServerParameters(command="scrapling", args=["mcp"])
}

mcp_session: dict[str, ClientSession] = {}

ALLOWED = {"get_current_time", "make_request"}
HIDDEN_TOOLS = {"make_request"}

# Make connection to MCP servers that are allowed
async def connect_mcp(stack: AsyncExitStack):
    for name, params in MCP_SERVERS.items():
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = (await session.list_tools()).tools
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
            schema = getattr(tool, "input_schema", None) or getattr(tool, "input_schema", None) \
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