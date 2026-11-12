import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse
import json
import shutil
import subprocess
import sys

import chromadb
import numpy as np

from config import WORKSPACE, QUERY_PREFIX, safe_path
from embed import get_embedder
from research_tool import fetch_page

_client = chromadb.PersistentClient(
    path=str(Path(__file__).parent / "chroma_db"),
    settings=chromadb.Settings(anonymized_telemetry=False),
)
_col = _client.get_or_create_collection("docs")


def _embed(texts):
    v = np.asarray(get_embedder().encode(texts, normalize_embeddings=True, batch_size=16),
                   dtype=np.float32)
    if v.ndim == 1:
        v = v[None]
    return (v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)).tolist()


def _split(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text):
        s = s.strip()
        if not s:
            continue
        while len(s) > size:
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:size])
            s = s[size - overlap:]
        if len(cur) + len(s) + 1 <= size:
            cur = f"{cur} {s}".strip()
        else:
            if cur:
                out.append(cur)
            tail = cur[-overlap:].split(" ", 1)[-1] if cur else ""
            cur = f"{tail} {s}".strip()
    if cur:
        out.append(cur)
    return [c for c in out if len(c) > 40]


def _extract(path: Path) -> list[tuple[str, str]]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        return [(f"p.{i + 1}", p.extract_text() or "") for i, p in enumerate(PdfReader(path).pages)]
    if ext == ".docx":
        from docx import Document
        d = Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return [("", "\n\n".join(parts))]
    if ext == ".doc":
        raise ValueError("old .doc not supported. Save as .docx first.")
    return [("", path.read_text(encoding="utf-8", errors="replace"))]


def _store(source: str, pieces: list[tuple[str, str]]) -> int:
    chunks = [(label, c) for label, text in pieces for c in _split(text)]
    if not chunks:
        return 0
    _col.delete(where={"source": source})
    step = 64
    for i in range(0, len(chunks), step):
        batch = chunks[i:i + step]
        _col.add(
            ids=[hashlib.md5(f"{source}:{i + j}".encode()).hexdigest() for j in range(len(batch))],
            documents=[c for _, c in batch],
            embeddings=_embed([c for _, c in batch]),
            metadatas=[{"source": source, "label": l, "idx": i + j}
                       for j, (l, _) in enumerate(batch)],
        )
        print(f" [rag] {min(i + step, len(chunks))}/{len(chunks)}")
    return len(chunks)


def ingest_doc(filename: str) -> str:
    path = safe_path(filename)
    if not path.is_file():
        return f"error: no file named {filename}"
    try:
        n = _store(filename, _extract(path))
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"
    if not n:
        return f"error: no text in {filename}. Scanned PDF? Needs OCR."
    return f"indexed: {filename}, {n} chunks"


async def ingest_url(url: str) -> str:
    import httpx
    p = urlparse(url)
    name = re.sub(r"\W+", "_", p.netloc + p.path)[:60].strip("_") or "page"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as h:
            r = await h.get(url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except Exception as e:
        return f"error: download failed: {type(e).__name__}: {e}"
    if "pdf" in r.headers.get("content-type", "").lower() or p.path.lower().endswith(".pdf"):
        name += ".pdf"
        (WORKSPACE / name).write_bytes(r.content)
    else:
        text = await fetch_page(url)
        if not text:
            return "error: page returned no text"
        name += ".md"
        (WORKSPACE / name).write_text(text, encoding="utf-8")
    return ingest_doc(name)


def search_docs(query: str, source: str = "") -> str:
    if _col.count() == 0:
        return "(no documents indexed)"
    kw = {"where": {"source": source}} if source else {}
    try:
        r = _col.query(query_embeddings=_embed(QUERY_PREFIX + query), n_results=4, **kw)
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"
    docs, metas = r["documents"][0], r["metadatas"][0]
    if not docs:
        return "(no match)"
    return "\n\n".join(f"[{m['source']} {m['label']}]\n{d[:800]}" for d, m in zip(docs, metas))


def _chunks_of(source: str):
    r = _col.get(where={"source": source}, include=["documents", "metadatas"])
    rows = sorted(zip(r["documents"], r["metadatas"]), key=lambda x: x[1]["idx"])
    return rows


def read_doc(source: str, part: int = 1) -> str:
    rows = _chunks_of(source)
    if not rows:
        return f"error: {source} not indexed. Call list_docs."
    per = 3
    total = (len(rows) + per - 1) // per
    if part < 1 or part > total:
        return f"error: part must be 1 to {total}"
    seg = rows[(part - 1) * per: part * per]
    labels = [m["label"] for _, m in seg if m["label"]]
    where = f", {labels[0]} to {labels[-1]}" if labels else ""
    body = "\n".join(d for d, _ in seg)
    return f"[{source} part {part}/{total}{where}]\n{body}"


def list_docs() -> str:
    r = _col.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for m in r["metadatas"]:
        counts[m["source"]] = counts.get(m["source"], 0) + 1
    if not counts:
        return "(no documents indexed)"
    return "\n".join(f"{s}: {n} chunks, {(n + 2) // 3} parts" for s, n in counts.items())


def remove_doc(source: str) -> str:
    _col.delete(where={"source": source})
    return f"removed: {source}"

def upload_doc() -> str:
    try:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "upload_ui.py")],
            capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "error: upload window timed out"
    try:
        paths = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return f"error: upload window failed: {r.stderr[-300:]}"
    if not paths:
        return "cancelled: no file chosen"
    out = []
    for p in paths:
        src = Path(p)
        shutil.copy(src, WORKSPACE / src.name)
        out.append(ingest_doc(src.name))
    return "\n".join(out)