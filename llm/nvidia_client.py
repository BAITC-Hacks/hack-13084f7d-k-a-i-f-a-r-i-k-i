"""NVIDIA NIM (OpenAI-совместимый API): эмбеддинги и резервный LLM. Все вызовы кэшируются."""
import os
import numpy as np
from dotenv import load_dotenv
from . import cache

load_dotenv()
_client = None


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("NVIDIA_API_KEY"),
                         base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"))
    return _client


def embed(texts: list[str], input_type: str = "passage") -> np.ndarray:
    """input_type: 'passage' для документов, 'query' для запросов (требуется retrieval-моделям NVIDIA)."""
    model = os.getenv("NVIDIA_EMBED_MODEL")
    if not model:
        raise RuntimeError("Не задан NVIDIA_EMBED_MODEL в .env")
    vecs, todo = [None] * len(texts), []
    for i, t in enumerate(texts):
        hit = cache.get("emb", {"m": model, "t": t, "it": input_type})
        if hit is None:
            todo.append(i)
        else:
            vecs[i] = hit
    for s in range(0, len(todo), 50):
        batch = todo[s:s + 50]
        r = client().embeddings.create(model=model, input=[texts[i] for i in batch],
                                       encoding_format="float",
                                       extra_body={"input_type": input_type, "truncate": "END"})
        for i, d in zip(batch, r.data):
            vecs[i] = cache.put("emb", {"m": model, "t": texts[i], "it": input_type}, d.embedding)
    a = np.array(vecs, dtype=np.float32)
    return a / np.linalg.norm(a, axis=1, keepdims=True)


def cosine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a @ b.T
