from file_tools import *
from mem_tools import *
from shell_tool import *
from web_tool import *
from mcp_client import mcp_session
from research_tool import research
from tools_schema import TOOL_SCHEMAS

# Local initialised tools
LOCAL_TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "save_memory": save_memory,
    "run_command": run_command,
    "edit_file": edit_file,
    "web_search": web_search
}

# Call tools mcp or local as nesessary
async def call_tool(name: str, args: dict) -> str:
    if name == "research":
        return await research(**args)
    if name in LOCAL_TOOLS:
        return LOCAL_TOOLS[name](**args)
    result = await mcp_session[name].call_tool(name, args)
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))[:5000]

def missing_args(name: str, args: dict) -> list[str]:
    for t in TOOL_SCHEMAS:
        f = t["function"]
        if f["name"] == name:
            return [k for k in f["parameters"].get("required", []) if k not in args]
    return []