import asyncio
import base64
import io
import os
import time
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from config import safe_path, WORKSPACE

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_SIDE = int(os.environ.get("OCR_MAX_SIDE", "2000"))
TIMEOUT = httpx.Timeout(60, connect=10)
POLL_EVERY = 3
JOB_LIMIT = int(os.environ.get("OCR_JOB_TIMEOUT", "420"))


def _prep(path: Path) -> str:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = img.size
    s = MAX_SIDE / max(w, h)
    if s < 1:
        img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def ocr_file_sync(path: Path, prompt: str = "Text Recognition:") -> str:
    base = os.environ.get("EMBED_BASE_URL")
    if not base:
        raise RuntimeError("EMBED_BASE_URL not set. OCR runs on the Kaggle server.")
    root = base.rstrip("/") + "/ocr"
    body = {"image": _prep(path), "prompt": prompt}
    jid, last = None, "OCR failed"
    for _ in range(3):
        try:
            r = httpx.post(root + "/start", json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            last = f"OCR server unreachable ({type(e).__name__}). Check EMBED_BASE_URL and Kaggle session."
            time.sleep(2)
            continue
        if r.status_code == 404:
            raise RuntimeError("OCR route missing on server. Re-run Kaggle embed_server cell.")
        if r.status_code != 200:
            last = f"OCR server returned {r.status_code}"
            time.sleep(2)
            continue
        jid = r.json()["id"]
        break
    if not jid:
        raise RuntimeError(last)
    end = time.time() + JOB_LIMIT
    while time.time() < end:
        time.sleep(POLL_EVERY)
        try:
            d = httpx.get(f"{root}/{jid}", timeout=TIMEOUT).json()
        except (httpx.HTTPError, ValueError):
            continue
        st = d.get("status")
        if st == "done":
            return d.get("text", "").strip()
        if st == "error":
            raise RuntimeError("OCR failed on server: " + d.get("error", "")[:200])
        if st == "missing":
            raise RuntimeError("OCR job lost, server restarted? Try again.")
    raise RuntimeError(f"OCR timed out after {JOB_LIMIT}s. Check Kaggle GPU.")


async def ocr_image(filename: str) -> str:
    try:
        path = safe_path(filename)
    except ValueError as e:
        return f"error: {e}"
    if not path.is_file():
        imgs = sorted(p.name for p in WORKSPACE.iterdir() if p.suffix.lower() in IMG_EXT)
        if len(imgs) == 1:
            filename = imgs[0]
            path = safe_path(filename)
        else:
            return (f"error: no file named {filename}. "
                    f"Images in workspace: {', '.join(imgs) or 'none'}. Use exact name.")
    if path.suffix.lower() not in IMG_EXT:
        return f"error: {filename} is not an image. Allowed: {', '.join(sorted(IMG_EXT))}"
    out_name = path.stem + ".ocr.md"
    out = safe_path(out_name)
    try:
        if out.is_file() and out.stat().st_mtime >= path.stat().st_mtime:
            text = out.read_text(encoding="utf-8")
        else:
            text = await asyncio.to_thread(ocr_file_sync, path)
            if not text:
                return f"error: no text found in {filename}."
            out.write_text(text, encoding="utf-8")
    except Exception as e:
        return f"error: {e}"
    from rag import ingest_doc
    res = await asyncio.to_thread(ingest_doc, out_name)
    if res.startswith("error:"):
        return res
    preview = " ".join(text.split())[:300]
    return (f"DONE. OCR text saved to {out_name}, {len(text)} chars. {res}. "
            f"Preview: {preview}. Use search_docs or read_doc for details.")