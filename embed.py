import os
import numpy as np
from config import EMBED_PATH

_embedder = None

class RemoteEmbedder:
    def __init__(self, base_url: str, model: str):
        from openai import OpenAI
        self.c = OpenAI(base_url=base_url, api_key="no-api")
        self.model = model

    def encode(self, texts, normalize_embeddings=True, batch_size=16, **kw):
        single = isinstance(texts, str)
        xs = [texts] if single else list(texts)
        out = []
        for i in range(0, len(xs), batch_size):
            r = self.c.embeddings.create(model=self.model, input=xs[i:i + batch_size])
            out += [d.embedding for d in r.data]
        v = np.array(out, dtype=np.float32)
        return v[0] if single else v

def get_embedder():
    global _embedder
    if _embedder is None:
        url = os.environ.get("EMBED_BASE_URL")
        if url:
            _embedder = RemoteEmbedder(url, EMBED_PATH)
        else:
            from sentence_transformers import SentenceTransformer
            try:
                _embedder = SentenceTransformer(EMBED_PATH, device="cpu")
            except Exception as e:
                raise RuntimeError(
                    f"embedding model '{EMBED_PATH}' is not in the local cache. "
                    f"Download it once with HF_HUB_OFFLINE unset. ({type(e).__name__})"
                ) from None
    return _embedder