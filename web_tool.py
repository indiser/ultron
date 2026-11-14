# import time
# from ddgs import DDGS

# # Helper fuction for Duck duck go search
# def ddg(query: str, n: int) -> list[dict]:
#     last = None
#     for _ in range(2):
#         try:
#             rs = DDGS().text(query, max_results=n + 3) or []
#             rs = [r for r in rs
#                   if "bing.com/aclick" not in r.get("href", "")
#                   and "duckduckgo.com/y.js" not in r.get("href", "")]
#             return rs[:n]
#         except Exception as e:
#             last = e
#             time.sleep(1.5)
#     raise last

# # Search The Web using deck duck go
# def web_search(query: str) -> str:
#     try:
#         results = ddg(query, 5)
#     except Exception as e:
#         return f"error: search failed twice: {e}"
#     return "\n\n".join(
#         f"{r['title']}\n{r['href']}\n{r['body']}" for r in results
#     ) or "(no results)"

import re, time
from ddgs import DDGS

def _variants(q: str) -> list[str]:
    v = [q,
         re.sub(r"\b(?:to|until|till)?\s*today\b", "2026", q, flags=re.I),
         " ".join(re.sub(r"\b(?:deep|research|major|list|all)\b", "", q, flags=re.I).split()[:6])]
    out = []
    for x in v:
        x = " ".join(x.split())
        if x and x not in out:
            out.append(x)
    return out

def ddg(query: str, n: int) -> list[dict]:
    last = None
    for q in _variants(query):
        for _ in range(2):
            try:
                rs = DDGS().text(q, max_results=n + 3) or []
                rs = [r for r in rs
                      if "bing.com/aclick" not in r.get("href", "")
                      and "duckduckgo.com/y.js" not in r.get("href", "")]
                if rs:
                    return rs[:n]
            except Exception as e:
                last = e
                print(f" [ddg] {type(e).__name__}: {e} (query: {q})")
                time.sleep(1.5)
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