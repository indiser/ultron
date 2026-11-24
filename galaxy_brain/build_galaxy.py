import json
import numpy as np
import umap

LOG = "../recall/chat_log.jsonl"
VEC = "../recall/vecs.npy"

rows = [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]
vecs = np.load(VEC)
print("log rows:", len(rows), "| vec shape:", vecs.shape)
print("first row keys:", list(rows[0].keys()))

n = min(len(rows), len(vecs))  # lazy embed: vecs may be shorter
rows, vecs = rows[:n], vecs[:n]

pts = umap.UMAP(
    n_components=3,
    n_neighbors=min(15, n - 1),
    min_dist=0.1,
    metric="cosine",
    random_state=42,
).fit_transform(vecs)

pts -= pts.mean(axis=0)
pts *= 100 / np.abs(pts).max()

out = [
    {
        "x": float(p[0]), "y": float(p[1]), "z": float(p[2]),
        "role": r["r"],
        "t": r["t"],
        "text": r["x"][:300],
    }
    for p, r in zip(pts, rows)
]
json.dump(out, open("galaxy.json", "w", encoding="utf-8"), indent = 4)
print("wrote galaxy.json:", len(out), "stars")