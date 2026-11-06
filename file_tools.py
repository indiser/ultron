import re
from pathlib import Path
from config import *

# File Look Up
def list_files() -> str:
    return "\n".join(p.name for p in WORKSPACE.iterdir()) or "(empty)"

# Read Files
def read_file(filename: str) -> str:
    path = safe_path(filename)
    if not path.is_file():
        return f"error: no file named {filename}"
    text = path.read_text(encoding="utf-8")
    if len(text) > 4000:
        return text[:4000] + f"\n[truncated, file has {len(text)} chars]"
    return text

# Write And Modify files
def write_file(filename: str, contents: str) -> str:
    if re.search(r"\[(?:Name \d+|Add more[^\]]*|List of[^\]]*)\]", contents, re.I):
        return "error: contents has placeholder text. Write only real content."
    safe_path(filename=filename).write_text(contents, encoding="utf-8")
    return f"wrote: {filename}"

# Edit a File
def edit_file(filename: str, old: str, new: str) -> str:
    path = safe_path(filename)
    if not path.is_file():
        return f"error: no file named {filename}"
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    if n == 0:
        return "error: old text not found. read_file first, copy exact text."
    if n > 1:
        return f"error: old text found {n} times. Include more surrounding lines."
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"edited: {filename}"