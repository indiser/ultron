import json
import re
import numpy as np
from embed import get_embedder
from config import QUERY_PREFIX, safe_path
from mcp_client import mcp_session
from web_tool import ddg
import asyncio
from timeline_rows import extract_timeline_rows

# Webpage markdown cleanup
def clean_markdown(text: str) -> str:
    # unwrap JSON if the tool returned JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "content" in data:
            data = data["content"]
        if isinstance(data, list):
            text = "\n".join(str(x) for x in data)
        elif isinstance(data, str):
            text = data
    except (json.JSONDecodeError, TypeError):
        pass
    if "\\n" in text:
        text = text.replace("\\n", "\n").replace('\\"', '"')
    text = re.sub(r"\[\[\d+\]\]\(#[^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

# Webpage markdown format analyze in chunks
def chunk_markdown(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            while len(p) > size:
                chunks.append(p[:size])
                p = p[size - overlap:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks

# Extract items from the markdown
def extract_items(text: str, min_run: int = 5) -> list[str]:
    runs, cur, expect = [], [], 1
    for line in clean_markdown(text).splitlines():
        m = re.match(r"^[#*\s]*(\d+)[\.\):\-]\s*(.{2,80})$", line)
        if not m or "↑" in line or "Retrieved" in line:
            continue
        n = int(m.group(1))
        name = re.sub(r"[*_`]", "", m.group(2)).strip()
        if n == expect:
            cur.append(name)
            expect += 1
        else:
            if len(cur) >= min_run:
                runs.append(cur)
            cur, expect = ([name], 2) if n == 1 else ([], 1)
    if len(cur) >= min_run:
        runs.append(cur)
    return max(runs, key=len) if runs else []

# Function to extract tables rows from a page
def extract_table_rows(text: str, min_run: int = 5) -> list[str]:
    runs, cur, expect = [], [], 1
    for line in clean_markdown(text).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [re.sub(r"\[[^\]]*\]", "", c).strip()
                 for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue

        name = next((c for c in cells[1:] if re.search(r"[A-Za-z]", c)), "")
        pop = next((c for c in cells[1:]
                    if re.fullmatch(r"\$?\d{1,3}(?:,\d{3})+|\$?\d{6,}", c)), "")
        if not name or not pop:
            continue
        n = int(cells[0])
        item = f"{name} - {pop}"
        if n == expect:
            cur.append(item)
            expect += 1
        else:
            if len(cur) >= min_run:
                runs.append(cur)
            cur, expect = ([item], 2) if n == 1 else ([], 1)
    if len(cur) >= min_run:
        runs.append(cur)
    return max(runs, key=len) if runs else []

# MinMax algo
def minmax(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    rng = a.max() - a.min()
    return np.zeros_like(a) if rng < 1e-9 else (a - a.min()) / rng

# Simplistic Pageranck algo for ranking pages
def pagerank(sim: np.ndarray, damping: float = 0.85, iters: int = 50) -> np.ndarray:
    n = len(sim)
    if n == 1:
        return np.ones(1)
    off = sim[~np.eye(n, dtype=bool)]
    w = np.clip(sim - np.median(off), 0, None)
    np.fill_diagonal(w, 0)
    col = w.sum(axis=0, keepdims=True)
    col[col == 0] = 1
    m = w / col
    r = np.ones(n) / n
    for _ in range(iters):
        r = (1 - damping) / n + damping * (m @ r)
    return r

# Bad stuff on webstie
def junk_ratio(text: str) -> float:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return 1.0
    bad = sum(1 for l in lines if l.startswith("|") or re.match(r"^\d+\.\s*[↑^]", l))
    return bad / len(lines)

# Score the webpage
def score_pages(query: str, pages: list[dict]) -> None:
    m = get_embedder()
    q = m.encode(QUERY_PREFIX + query, normalize_embeddings=True)
    best_sim, page_vecs = [], []
    for p in pages:
        v = m.encode(p["chunks"], normalize_embeddings=True, batch_size=16)
        s = v @ q
        p["chunk_scores"] = s
        best_sim.append(float(np.sort(s)[::-1][:3].mean()))
        mv = v.mean(axis=0)
        page_vecs.append(mv / (np.linalg.norm(mv) + 1e-9))
    pv = np.array(page_vecs)
    pr = pagerank(pv @ pv.T)
    rrf = np.array([1.0 / (60 + p["rank"]) for p in pages])
    final = 0.45 * minmax(best_sim) + 0.25 * minmax(pr) + 0.30 * minmax(rrf)
    for p, f, bs, r_ in zip(pages, final, best_sim, pr):
        p["final"] = float(f * (1 - 0.6 * junk_ratio(p["text"])))
        p["match"], p["pr"] = bs, float(r_)

# Turn the webpage into markdown
async def fetch_page(url: str) -> str:
    try:
        # res = await mcp_session["make_request"].call_tool("make_request", {"url": url})
        res = await asyncio.wait_for(
            mcp_session["make_request"].call_tool("make_request", {"url": url}), timeout=25)
        text = "\n".join(c.text for c in res.content if hasattr(c, "text"))
        return clean_markdown(text)[:150000]
    except Exception:
        return ""

# Complete deep research on the web
async def research(query: str, save_to: str = "", top_k: int = 3) -> str:
    try:
        results = await asyncio.to_thread(ddg, query, 8)
    except Exception as e:
        return f"error: search failed: {e}"
    cand = (results or [])[:5]
    if not cand:
        return "error: no search results"
    texts = await asyncio.gather(*(fetch_page(r["href"]) for r in cand))
    pages = []
    for rank, (r, t) in enumerate(zip(cand, texts)):
        if len(t) < 300:
            continue
        chunks = chunk_markdown(t)[:120]
        if chunks:
            pages.append({"url": r["href"], "title": r.get("title", ""), "rank": rank,
                          "text": t, "chunks": chunks})
    if not pages:
        return "error: no page returned usable text"
    await asyncio.to_thread(score_pages, query, pages)
    pages.sort(key=lambda p: -p["final"])
    for p in pages:
        print(f" [research] final={p['final']:.2f} match={p['match']:.2f} "
              f"pr={p['pr']:.2f} rank={p['rank']} {p['url']}")
    
    mt = re.search(r"\b(?:top|best)\s+(\d+)|\b(\d+)\s+(?:largest|biggest|top|best|most)", query, re.I)
    want = int(mt.group(1) or mt.group(2)) if mt else 10
    need = max(5, int(want * 0.8))
    if save_to:
        for p in pages:
            # items = next((c for c in (extract_table_rows(p["text"]), extract_items(p["text"]))
            #               if len(c) >= need), [])
            items = next((c for c in (extract_table_rows(p["text"]), extract_items(p["text"]),
                        extract_timeline_rows(p["text"]))
                          if len(c) >= need), [])
            if not items:
                rows = [l[:250] for l in p["text"].splitlines() if l.lstrip().startswith("|")]
                print(f" [debug] {p['url']} len={len(p['text'])} table_lines={len(rows)}")
                for r in rows[:6]:
                    print(" [debug]", r)
            if save_to.lower().endswith(".csv") and not all(
                    re.search(r"\d{1,3}(?:,\d{3}){2,}|\d{7,}", it) for it in items):
                items = []
            if mt:
                items = items[:want]
            print(f" [research] {len(items)} numbered items (need {need}) {p['url']}")
            if len(items) >= need:
                # out = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(items))
                if save_to.lower().endswith(".csv"):
                    rows = []
                    for i, it in enumerate(items):
                        name, _, val = it.rpartition(" - ")
                        name = name.replace('"', '""')
                        val = val.replace("$", "").replace(",", "")
                        rows.append(f'{i + 1},"{name}",{val}')
                    out = "rank,name,value\n" + "\n".join(rows)
                else:
                    out = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(items))
                safe_path(save_to).write_text(out, encoding="utf-8")
                return (
                    f"DONE. All {len(items)} items saved to {save_to}. "
                    f"Source: {p['url']} (page title: {p['title']}). "
                    f"Preview of first 5 only: {', '.join(items[:5])}. "
                    f"Tell the user the file is complete with {len(items)} items."
                )
        return (f"error: no ranked page had a clean numbered list of {need}+ items. Tried:\n"
        + "\n".join(p["url"] for p in pages))

    best = pages[0]
    order = np.argsort(-best["chunk_scores"])[:2]
    parts = [f"[1] {best['chunks'][i][:1200]}" for i in order]
    for n, p in enumerate(pages[1:3], start=2):
        j = int(np.argmax(p["chunk_scores"]))
        parts.append(f"[{n + 1}] (from {p['url']}) {p['chunks'][j][:800]}")
    body = "\n\n---\n\n".join(parts)
    others = ", ".join(p["url"] for p in pages[1:3])
    items = extract_items(best["text"])
    if len(items) >= 5:
        body += "\n\nNumbered items on this page: " + "; ".join(items[:50])[:1500]
    return f"Best source: {best['url']}\nOther sources: {others}\n\n{body}"