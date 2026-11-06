import sys
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding= "utf-8")
import os
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(
    base_url = os.environ.get("BRAIN_LLM_BASE_URL"),
    api_key = "no-api"
)
MODEL = os.environ.get("BRAIN_LLM_NAME")

WORKSPACE = Path(__file__).parent/"workspace"
os.makedirs(WORKSPACE, exist_ok=True)

MEMORY_FILE = Path(__file__).parent/"memory.md"

VENV = Path(__file__).parent / ".venv"

EMBED_PATH = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def safe_path(filename: str) -> Path:
    path = (WORKSPACE / filename).resolve()
    if not path.is_relative_to(WORKSPACE.resolve()):
        raise ValueError("path outside workspace")
    return path
