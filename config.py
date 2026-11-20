import sys
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding= "utf-8")
import os
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv
import httpx

load_dotenv()

client = AsyncOpenAI(
    base_url = os.environ.get("BRAIN_LLM_BASE_URL"),
    api_key = "no-api",
    max_retries = 2,
    timeout = httpx.Timeout(300.0, connect=20.0),
)
MODEL = os.environ.get("BRAIN_LLM_NAME")

WORKSPACE = Path(__file__).parent/"workspace"
os.makedirs(WORKSPACE, exist_ok=True)

MEMORY_FILE = Path(__file__).parent/"memory.md"

VENV = Path(__file__).parent / ".venv"

LOCATION_FILE = Path(__file__).parent / "location.json"
SCHEDULES_FILE = Path(__file__).parent / "schedules.json"  # or os.path.join(..., "schedules.json") matching your config.py style

EMBED_PATH = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def safe_path(filename: str) -> Path:
    path = (WORKSPACE / filename).resolve()
    if not path.is_relative_to(WORKSPACE.resolve()):
        raise ValueError("path outside workspace")
    return path
