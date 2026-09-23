"""Шаг 3. Сопоставление подразделений «до ↔ после».   Владелец: роль 1.

Выход: list[UnitMap], status: kept | renamed | merged | split | abolished | created | modified.

Алгоритм (TODO):
1. Прочитать распорядительный документ (приказ) — чанки side=after без раздела «Функции»;
   LLM (сильная модель) извлекает явные указания: объединить / упразднить / переименовать / создать.
2. Для подразделений, не упомянутых в приказе: совпадение кода/названия → kept или modified
   (modified, если набор функций изменился).
3. Для оставшихся: сходство функций (эмбеддинги) → кандидаты → LLM-решение.
4. Evidence: пункт приказа + строки оргструктур.
Сейчас: baseline по совпадению кодов — чтобы пайплайн работал сквозным.
"""
from .schemas import UnitMap


def match_units(units, functions, chunks, log=print) -> list[UnitMap]:
    before = {u["code"]: u for u in units if u["side"] == "before"}
    after = {u["code"]: u for u in units if u["side"] == "after"}
    fset = lambda uid: {f["text"] for f in functions if f["unit_id"] == uid}
    out = []
    for code, u in before.items():
        if code in after:
            same = fset(u["unit_id"]) == fset(after[code]["unit_id"])
            out.append({"before_ids": [u["unit_id"]], "after_ids": [after[code]["unit_id"]],
                        "status": "kept" if same else "modified", "rationale": "совпадает код подразделения",
                        "evidence": []})
        else:
            out.append({"before_ids": [u["unit_id"]], "after_ids": [], "status": "abolished",
                        "rationale": "BASELINE: нет подразделения с тем же кодом — TODO уточнить по приказу",
                        "evidence": []})
    for code, u in after.items():
        if code not in before:
            out.append({"before_ids": [], "after_ids": [u["unit_id"]], "status": "created",
                        "rationale": "BASELINE: нет подразделения с тем же кодом — TODO уточнить по приказу",
                        "evidence": []})
    log(f"Подразделения: сопоставлено {len(out)} записей (baseline)")
    return out
