import asyncio
import io
import json
import re
import shutil
import time
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from interrupt import ask
from skills_tool import SKILLS_DIR, load_skills, parse_text, tree_hash

MAX_ZIP = 30 * 1024 * 1024
MAX_UNPACKED = 5 * 1024 * 1024
MAX_FILES = 100
BAD_EXT = {".exe", ".dll", ".so", ".dylib", ".msi", ".jar", ".apk", ".com", ".scr", ".bin"}
SCRIPT_EXT = {".py", ".sh", ".ps1", ".bat", ".cmd", ".js", ".ts", ".rb", ".pl"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def parse_source(src: str):
    s = src.strip().removesuffix(".git").rstrip("/")
    s = re.sub(r"^https?://(www\.)?github\.com/", "", s)
    parts = [p for p in s.split("/") if p]
    if len(parts) < 2:
        raise ValueError("source must be owner/repo[/path] or a github.com link")
    owner, repo, rest = parts[0], parts[1], parts[2:]
    branch = None
    if rest[:1] in (["tree"], ["blob"]) and len(rest) >= 2:
        branch, rest = rest[1], rest[2:]
    path = "/".join(rest)
    if path.endswith("SKILL.md"):
        path = path[:-8].rstrip("/")
    return owner, repo, branch, path


def source_in_text(src: str, text: str) -> bool:
    try:
        owner, repo, _, _ = parse_source(src)
    except ValueError:
        return False
    return f"{owner}/{repo}".lower() in text.lower()


async def _download(owner: str, repo: str, branch) -> bytes:
    ref = f"refs/heads/{branch}" if branch else "HEAD"
    url = f"https://github.com/{owner}/{repo}/archive/{ref}.zip"
    buf = bytearray()
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as h:
        async with h.stream("GET", url, headers={"User-Agent": "UltronAgent/1.0"}) as r:
            if r.status_code == 404:
                raise ValueError(f"repo or branch not found: {owner}/{repo}")
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                buf += chunk
                if len(buf) > MAX_ZIP:
                    raise ValueError("repo zip is over 30 MB, refusing")
    return bytes(buf)


def _find(z: zipfile.ZipFile, path: str) -> str:
    names = z.namelist()
    root = names[0].split("/")[0] + "/"
    if path:
        base = root + path.strip("/") + "/"
        if base + "SKILL.md" in names:
            return base
        sub = sorted({n[len(base):].split("/")[0] for n in names if n.startswith(base) and n.endswith("/SKILL.md")})
        if sub:
            raise ValueError(f"'{path}' holds {len(sub)} skills, none is this folder. Pick one: {', '.join(sub[:30])}")
        raise ValueError(f"no SKILL.md at '{path}'")
    dirs = sorted({n[:-8] for n in names if n == root + "SKILL.md" or n.endswith("/SKILL.md")})
    if len(dirs) == 1:
        return dirs[0]
    if not dirs:
        raise ValueError("no SKILL.md found in repo")
    shown = ", ".join(d[len(root):].rstrip("/") or "(root)" for d in dirs[:20])
    raise ValueError(f"repo has {len(dirs)} skills. Give owner/repo/<path>. Found: {shown}")


def _extract(z: zipfile.ZipFile, base: str, dest: Path):
    infos = [i for i in z.infolist() if i.filename.startswith(base) and not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise ValueError(f"{len(infos)} files, limit {MAX_FILES}")
    total = sum(i.file_size for i in infos)
    if total > MAX_UNPACKED:
        raise ValueError(f"{total // 1024} KB unpacked, limit {MAX_UNPACKED // 1024} KB")
    files, scripts = [], []
    root = dest.resolve()
    for i in infos:
        rel = PurePosixPath(i.filename[len(base):])
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("unsafe path in zip")
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("symlink in zip")
        if rel.suffix.lower() in BAD_EXT:
            raise ValueError(f"binary file in skill: {rel}")
        out = dest.joinpath(*rel.parts)
        if not out.resolve().is_relative_to(root):
            raise ValueError("unsafe path in zip")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(z.read(i))
        files.append(str(rel))
        if rel.suffix.lower() in SCRIPT_EXT:
            scripts.append(str(rel))
    return files, scripts, total


async def install_skill(source: str) -> str:
    staging = None
    try:
        owner, repo, branch, path = parse_source(source)
        z = zipfile.ZipFile(io.BytesIO(await _download(owner, repo, branch)))
        base = _find(z, path)
        meta = parse_text(z.read(base + "SKILL.md").decode("utf-8", errors="replace"))
        if not meta:
            return "error: SKILL.md has no valid front matter (name, description)."
        name = meta["name"]
        if not NAME_RE.match(name):
            return f"error: unsafe skill name '{name}'."
        dest = SKILLS_DIR / name
        if dest.exists():
            return f"error: skill '{name}' already installed. User can delete skills/{name} to reinstall."
        staging = SKILLS_DIR / f".staging-{name}"
        shutil.rmtree(staging, ignore_errors=True)
        files, scripts, total = _extract(z, base, staging)
        print(f"\n Skill: {name}   from {owner}/{repo}/{path}".rstrip("/"))
        print(f" Description: {meta['desc']}")
        if meta["compat"]:
            print(f" Compatibility: {meta['compat']}")
        print(f" Files: {len(files)}, {total // 1024} KB")
        print(f" Scripts: {', '.join(scripts) if scripts else 'none'}")
        print(" Instructions start:\n   " + meta["body"][:600].replace("\n", "\n   "))
        ans = await asyncio.to_thread(ask, f"\n Install skill '{name}'? [y/N] ")
        if ans.strip().lower() != "y":
            return "The user declined to install this skill. Do not retry."
        SKILLS_DIR.mkdir(exist_ok=True)
        shutil.move(str(staging), str(dest))
        staging = None
        (dest / ".source.json").write_text(json.dumps({
            "source": f"{owner}/{repo}/{path}", "sha256": tree_hash(dest),
            "installed": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
        load_skills()
        return (f"installed skill: {name}. Scripts: {', '.join(scripts) if scripts else 'none'}. "
                f"It activates when a request matches: {meta['desc'][:150]}")
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)


def remove_skill(name: str) -> str:
    if not NAME_RE.match(name) or not (SKILLS_DIR / name).is_dir():
        return f"no skill named '{name}'"
    shutil.rmtree(SKILLS_DIR / name)
    load_skills()
    return f"removed skill: {name}"