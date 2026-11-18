import re, time
from ddgs import DDGS

_STOP = {"the", "a", "an", "is", "are", "of", "for", "in", "on", "to", "what",
         "latest", "current", "national", "number", "version", "patch"}

# def _variants(q: str) -> list[str]:
#     v = [q,
#          re.sub(r"\b(?:to|until|till)?\s*today\b", "2026", q, flags=re.I),
#          " ".join(re.sub(r"\b(?:deep|research|major|list|all)\b", "", q, flags=re.I).split()[:6])]
#     out = []
#     for x in v:
#         x = " ".join(x.split())
#         if x and x not in out:
#             out.append(x)
#     return out

def _variants(q: str) -> list[str]:
    core = [w for w in re.findall(r"[A-Za-z0-9.]+", q) if w.lower() not in _STOP]
    v = [
        q,
        re.sub(r"\b(?:to|until|till)?\s*today\b", "2026", q, flags=re.I),
        " ".join(re.sub(r"\b(?:deep|research|major|list|all)\b", "", q, flags=re.I).split()[:6]),
        " ".join(core[:4]),
    ]
    out = []
    for x in v:
        x = " ".join(x.split())
        if x and x not in out:
            out.append(x)
    return out

# def ddg(query: str, n: int) -> list[dict]:
#     last = None
#     for q in _variants(query):
#         for _ in range(2):
#             try:
#                 rs = DDGS().text(q, max_results=n + 3) or []
#                 rs = [r for r in rs
#                       if "bing.com/aclick" not in r.get("href", "")
#                       and "duckduckgo.com/y.js" not in r.get("href", "")]
#                 if rs:
#                     return rs[:n]
#             except Exception as e:
#                 last = e
#                 print(f" [ddg] {type(e).__name__}: {e} (query: {q})")
#                 time.sleep(1.5)
#     raise last or RuntimeError("no results")

def ddg(query: str, n: int) -> list[dict]:
    last = None
    for q in _variants(query):
        for backend in ("auto", "lite"):
            try:
                rs = DDGS().text(q, max_results=n + 3, backend=backend) or []
                rs = [r for r in rs
                      if "bing.com/aclick" not in r.get("href", "")
                      and "duckduckgo.com/y.js" not in r.get("href", "")]
                if rs:
                    return rs[:n]
            except Exception as e:
                last = e
                print(f" [ddg:{backend}] {type(e).__name__}: {e} (query: {q})")
                time.sleep(1.0)
    raise last or RuntimeError("no results")

# # Search The Web using deck duck go
def web_search(query: str) -> str:
    try:
        results = ddg(query, 5)
    except Exception as e:
        return f"error: search failed twice: {e}"
    return "\n\n".join(
        f"{r['title']}\n{r['href']}\n{r['body']}" for r in results
    ) or "(no results)"