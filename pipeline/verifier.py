"""Шаг 6. Верификатор цитат: вывод без подтверждённой цитаты не попадает в отчёт.   Владелец: роль 3."""
import os
from rapidfuzz import fuzz

THRESHOLD = int(os.getenv("VERIFY_THRESHOLD", 90))


def _norm(s: str) -> str:
    return " ".join(s.replace("ё", "е").replace("Ё", "Е").lower().split())


def quote_found(quote: str, text: str, threshold: int = THRESHOLD) -> bool:
    q, t = _norm(quote), _norm(text)
    if not q:
        return False
    return q in t or fuzz.partial_ratio(q, t) >= threshold


def verify(findings: list, chunks: list, log=print):
    """Возвращает (verified, rejected). Evidence ищется в чанках того же документа."""
    by_doc = {}
    for c in chunks:
        by_doc.setdefault((c["side"], c["doc_name"]), []).append(c)
    ok, bad = [], []
    for f in findings:
        notes = []
        if not f.get("evidence"):
            notes.append("нет evidence")
        for e in f.get("evidence", []):
            doc_chunks = by_doc.get((e.get("side"), e.get("doc_name")), [])
            if not any(quote_found(e.get("quote", ""), c["text"]) for c in doc_chunks):
                notes.append(f"цитата не найдена в {e.get('doc_name')} п.{e.get('clause')}")
        f = dict(f, verified=not notes, verify_note="; ".join(notes))
        (ok if not notes else bad).append(f)
    log(f"Верификатор: подтверждено {len(ok)}, отклонено {len(bad)}")
    return ok, bad
