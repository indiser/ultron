"""recall: search past conversations. No new deps (numpy + your embedder).

Files (auto-created next to this file):
  recall/chat_log.jsonl   one JSON line per turn   {"t": "2026-11-20 18:03", "r": "user|assistant", "x": "text"}
  recall/vecs.npy         one embedding row per log line, same order
Delete the recall/ folder (or call clear_history) to forget everything.
"""
import json
import os
import time
from pathlib import Path

import numpy as np

from config import QUERY_PREFIX
from embed import get_embedder

DIR = Path(__file__).parent / "recall"
LOG = DIR / "chat_log.jsonl"
VEC = DIR / "vecs.npy"
KEEP = 600          # chars stored per turn (bge-small reads about 256 tokens)
MIN_CHARS = 12      # skips "stop", "yeah", "ok"
MIN_SIM = float(os.environ.get("RECALL_MIN", "0.45"))   # untuned, adjust from real hits


def log_turn(role: str, text: str) -> None:
    """Call after each finished turn. Cheap: file append only, no network."""
    text = " ".join((text or "").split())[:KEEP]
    if len(text) < MIN_CHARS or text.startswith("error:"):
        return
    DIR.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M"), "r": role, "x": text},
                           ensure_ascii=False) + "\n")


def clear_history() -> str:
    n = 0
    for p in (LOG, VEC):
        if p.is_file():
            p.unlink()
            n += 1
    return "chat history cleared" if n else "no chat history to clear"


def _rows() -> list:
    if not LOG.is_file():
        return []
    out = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _vectors(rows: list) -> np.ndarray:
    """Embed only turns not embedded yet. Saves after every chunk. Stops at 60 s (tunnel limit)."""
    have = np.load(VEC) if VEC.is_file() else np.zeros((0, 0), np.float32)
    if have.shape[0] > len(rows):               # log was edited or shrunk: rebuild
        have = np.zeros((0, 0), np.float32)
    deadline = time.time() + 60
    while have.shape[0] < len(rows) and time.time() < deadline:
        chunk = rows[have.shape[0]: have.shape[0] + 64]
        add = np.asarray(get_embedder().encode([r["x"] for r in chunk], normalize_embeddings=True,
                                               batch_size=16), dtype=np.float32)
        if add.ndim == 1:
            add = add[None, :]
        if have.shape[0] and have.shape[1] != add.shape[1]:    # embedder changed: start over
            have = np.zeros((0, 0), np.float32)
            continue
        have = add if have.shape[0] == 0 else np.vstack([have, add])
        np.save(VEC, have)
    return have


def recall(query: str = "", days_back=None, limit: int = 5, **_) -> str:
    q = (query or "").strip()
    if not q:
        return "error: recall needs a query"
    rows = _rows()
    if not rows:
        return "no saved chat history yet"
    try:
        vecs = _vectors(rows)
        qv = np.asarray(get_embedder().encode(QUERY_PREFIX + q, normalize_embeddings=True),
                        dtype=np.float32).reshape(-1)
        n = vecs.shape[0]
        sims = vecs @ qv
    except Exception as e:
        return f"error: embeddings failed: {type(e).__name__}: {e}"

    try:
        days = int(days_back) if days_back not in (None, "") else None
    except (TypeError, ValueError):
        days = None
    if days:
        cutoff = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - days * 86400))
        sims = np.where(np.array([r["t"] >= cutoff for r in rows[:n]]), sims, -1.0)

    out, shown = [], set()
    for i in np.argsort(-sims):
        if len(out) >= limit or sims[i] < MIN_SIM:
            break
        if i in shown:
            continue
        shown.add(i)
        r = rows[i]
        if r["r"] == "user":
            line = f"[{r['t']}] you: {r['x'][:300]}"
            j = i + 1
            if j < len(rows) and rows[j]["r"] == "assistant":
                shown.add(j)
                line += f"\n  ultron answered: {rows[j]['x'][:200]}"
        else:
            line = f"[{r['t']}] ultron: {r['x'][:300]}"
            j = i - 1
            if j >= 0 and rows[j]["r"] == "user":
                shown.add(j)
                line = f"[{rows[j]['t']}] you asked: {rows[j]['x'][:200]}\n  " + line.split("] ", 1)[1]
        out.append(line)

    note = f"\n(indexed {n} of {len(rows)} turns, call again to continue)" if n < len(rows) else ""
    if not out:
        return "no match in saved chats" + (f" for the last {days} days" if days else "") + note
    return ("\n".join(out))[:2500] + note