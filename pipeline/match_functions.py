"""Шаг 4. Судьба каждой функции «до»: covered | partial | lost.   Владелец: роль 1 (эмбеддинги — роль 3).

Алгоритм (TODO):
1. Эмбеддинги всех функций (llm.nvidia_client.embed), косинус «до» × «после».
2. Для каждой функции «до» — топ-5 кандидатов из ВСЕХ подразделений «после» (не только наследника!).
3. score >= HIGH → covered без LLM; score < LOW → lost без LLM; середина → LLM-судья
   (covered / partial / lost + rationale + quote).
4. lost → Finding(type="loss") с evidence на пункт «до» и, если есть, пункт приказа.
Сейчас: baseline на rapidfuzz, без LLM.
"""
from rapidfuzz import fuzz
from .schemas import FunctionMap

HIGH, LOW = 85, 60


def match_functions(functions, unit_map, log=print) -> list[FunctionMap]:
    before = [f for f in functions if f["unit_id"].startswith("before:")]
    after = [f for f in functions if f["unit_id"].startswith("after:")]
    out = []
    for f in before:
        scored = sorted(((fuzz.token_set_ratio(f["text"], g["text"]), g) for g in after),
                        key=lambda x: -x[0])[:3]
        best = scored[0][0] if scored else 0
        status = "covered" if best >= HIGH else "lost" if best < LOW else "partial"
        out.append({"func_id": f["func_id"], "status": status,
                    "matched_func_ids": [g["func_id"] for s, g in scored if s >= LOW],
                    "score": round(best / 100, 3), "rationale": "BASELINE rapidfuzz"})
    log(f"Функции: lost={sum(x['status']=='lost' for x in out)}, "
        f"partial={sum(x['status']=='partial' for x in out)} (baseline)")
    return out
