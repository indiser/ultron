import re

# Rows like "| 1947 | Independence of India, ... |" from a Year | Event table.
def extract_timeline_rows(text: str, min_run: int = 5) -> list[str]:
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\s*\|\s*(\d{4}(?:\s*[-–]\s*\d{2,4})?)\s*\|\s*(.+?)\s*\|\s*$", line)
        if not m:
            continue
        year, event = m.group(1), re.sub(r"[*_`]|\[[^\]]*\]", "", m.group(2)).strip()
        if 1800 <= int(year[:4]) <= 2100 and len(event) > 10:
            rows.append(f"{year} - {event}")
    seen, out = set(), []
    for r in rows:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out if len(out) >= min_run else []