from config import safe_path
from mcp_client import mcp_session

TOOL = "convert-contents"

IN_FMT = {
    ".md": "markdown", ".markdown": "markdown", ".html": "html", ".htm": "html",
    ".txt": "txt", ".docx": "docx", ".rst": "rst", ".tex": "latex",
    ".epub": "epub", ".ipynb": "ipynb", ".odt": "odt",
}
OUT_EXT = {"docx": ".docx", "html": ".html", "epub": ".epub", "odt": ".odt", "txt": ".txt"}


async def export_doc(filename: str, format: str = "docx") -> str:
    fmt = (format or "").lower().lstrip(".")
    if fmt not in OUT_EXT:
        return f"error: format must be one of {sorted(OUT_EXT)}"
    try:
        src = safe_path(filename)
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"
    if not src.is_file():
        return f"error: no file named {filename}"
    in_fmt = IN_FMT.get(src.suffix.lower())
    if not in_fmt:
        return f"error: cannot convert from {src.suffix}. Supported: {sorted(IN_FMT)}"
    out = src.with_suffix(OUT_EXT[fmt])
    if out == src:
        return "error: source and target format are the same"
    if out.exists():
        return f"error: {out.name} already exists. Use delete_file first or pick another format."
    session = mcp_session.get(TOOL)
    if session is None:
        return "error: pandoc MCP not connected. Check pandoc and uvx are installed."
    args = {
        "input_file": str(src.resolve()),
        "input_format": in_fmt,
        "output_format": fmt,
        "output_file": str(out.resolve()),
    }
    try:
        res = await session.call_tool(TOOL, args)
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"
    msg = " ".join(getattr(c, "text", "") or "" for c in res.content)[:300]
    if getattr(res, "isError", False) or not out.is_file():
        return f"error: conversion failed: {msg}"
    return f"DONE. saved {out.name}, {out.stat().st_size} bytes in workspace."