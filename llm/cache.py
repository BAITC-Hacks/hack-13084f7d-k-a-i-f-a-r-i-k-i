"""Дисковый кэш ответов LLM и эмбеддингов: экономит деньги и делает демо мгновенным."""
import hashlib, json, os
from pathlib import Path

CACHE_DIR = Path(os.getenv("CACHE_DIR", ".cache"))


def _path(kind: str, payload) -> Path:
    h = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
    return CACHE_DIR / kind / f"{h}.json"


def get(kind, payload):
    p = _path(kind, payload)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def put(kind, payload, value):
    p = _path(kind, payload)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value
