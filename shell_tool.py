from config import *
import re
import subprocess
import os

def venv_env() -> dict:
    if not VENV.exists():
        subprocess.run(["uv", "venv", "--seed", str(VENV)], check=True, capture_output=True)
    bindir = VENV / ("Scripts" if os.name == "nt" else "bin")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    env["VIRTUAL_ENV"] = str(VENV)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    return env

# Run commands in the terminal
def run_command(command: str):
    if re.search(r"python\S*\s+-c\s.*;\s*(for|with|if|while|def)\b", command):
        return "error: python -c cannot hold for/with/if on one line. write_file a .py script, then run python name.py"
    answer = input(f"\n Run '{command}'? [y/N]")
    if answer.strip().lower() != 'y':
        return "The user declined to run this command"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text = True, timeout = 120, cwd= WORKSPACE, encoding="utf-8", errors="replace", env=venv_env()
        )
    except subprocess.TimeoutExpired:
        return "error: command timed out after 120s"
    except subprocess.CalledProcessError as e:
        return f"error: venv create failed: {e}"
    
    output = (result.stdout + result.stderr).strip()
    print(f"\n [Command Result] {output[-2000:]}")
    return output[-3000:] or f"(no output, exit code {result.returncode})"