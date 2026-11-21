import asyncio, os, re, shutil, sys
from asyncio.subprocess import PIPE, STDOUT
from pathlib import Path
from config import WORKSPACE

REPOS = WORKSPACE / "repos"
REPOS.mkdir(parents=True, exist_ok=True)
URL_RE = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
SAFE_ENV = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LANG")
VBIN = "Scripts" if os.name == "nt" else "bin"

import difflib

def _resolve(name: str) -> str | None:
    names = [p.name for p in REPOS.iterdir() if p.is_dir()]
    if name in names:
        return name
    hit = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
    if hit:
        return hit[0]
    key = name.lower().replace("_", "").replace("/", "")
    return next((n for n in names if key in n.lower().replace("_", "")), None)

def _dir(name: str) -> Path:
    d = (REPOS / name).resolve()
    if d.parent != REPOS.resolve():
        raise ValueError("bad repo name")
    return d


def _env(d: Path) -> dict:
    env = {k: os.environ[k] for k in SAFE_ENV if k in os.environ}  # no API keys, no Telegram token
    v = d / ".venv"
    if v.exists():
        env["PATH"] = str(v / VBIN) + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(v)
    return env


async def _sh(cmd: str, d: Path, timeout: int = 300) -> str:
    p = await asyncio.create_subprocess_shell(cmd, cwd=d, env=_env(d), stdout=PIPE, stderr=STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        return f"error: timeout after {timeout}s"
    return f"exit {p.returncode}\n" + out.decode(errors="replace")[-4000:]


async def repo(action: str, url: str = "", name: str = "", command: str = "", timeout: int = 300) -> str:
    try:
        if action == "list":
            return "\n".join(p.name for p in REPOS.iterdir() if p.is_dir()) or "no repos"

        if action == "clone":
            m = URL_RE.match(url.strip())
            if not m:
                return "error: need https://github.com/owner/name"
            name = f"{m[1]}__{m[2]}"
            d = _dir(name)
            if d.exists():
                return f"already cloned: {name}"
            out = await _sh(f'git clone --depth 1 "{url}" "{d}"', REPOS, 180)
            return f"{name}\n{out}\nNext: repo info name={name}"
        real = _resolve(name)
        if not real:
            return "error: no repo " + repr(name) + ". Cloned: " + (", ".join(p.name for p in REPOS.iterdir() if p.is_dir()) or "none")
        name = real
        d = _dir(name)
        if not d.is_dir():
            return f"error: no repo {name}. Use action list."

        if action == "info":
            readme = next((p for p in d.glob("README*")), None)
            files = sorted(x.name for x in d.iterdir() if x.name != ".git")[:60]
            return ("files: " + ", ".join(files) + "\n\nREADME:\n"
                    + (readme.read_text(errors="replace")[:3000] if readme else "none"))

        if action == "setup":
            if (d / "requirements.txt").exists() or (d / "pyproject.toml").exists():
                cmd = f'"{sys.executable}" -m venv .venv && python -m pip install -q ' + (
                    "-r requirements.txt" if (d / "requirements.txt").exists() else "-e .")
            elif (d / "package.json").exists():
                cmd = "npm install --ignore-scripts"
            else:
                return "error: no requirements.txt, pyproject.toml or package.json"
            return await _sh(cmd, d, 900)

        if action == "run":
            if not command:
                return "error: command needed"
            return await _sh(command, d, max(5, min(int(timeout), 900)))

        if action == "remove":
            shutil.rmtree(d, ignore_errors=True)
            return f"removed {name}"

        return "error: action must be clone, list, info, setup, run, remove"
    except Exception as e:
        return f"error: {e}"