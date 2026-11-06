import time
from ddgs import DDGS

# Helper fuction for Duck duck go search
def ddg(query: str, n: int) -> list[dict]:
    last = None
    for _ in range(2):
        try:
            rs = DDGS().text(query, max_results=n + 3) or []
            rs = [r for r in rs
                  if "bing.com/aclick" not in r.get("href", "")
                  and "duckduckgo.com/y.js" not in r.get("href", "")]
            return rs[:n]
        except Exception as e:
            last = e
            time.sleep(1.5)
    raise last

# Search The Web using deck duck go
def web_search(query: str) -> str:
    try:
        results = ddg(query, 5)
    except Exception as e:
        return f"error: search failed twice: {e}"
    return "\n\n".join(
        f"{r['title']}\n{r['href']}\n{r['body']}" for r in results
    ) or "(no results)"