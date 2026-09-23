# Контракты данных — ИСТОЧНИК ПРАВДЫ

Любое изменение формата — только через тимлида и одним коммитом сюда + в `pipeline/schemas.py`.
Все модули обмениваются этими структурами (dict / JSON). Агентам (Codex, Ouroboros) давать этот файл в каждом промпте.

## Chunk — фрагмент документа (выход parse.py)
```json
{"chunk_id": "before/02_Положение_ДЗ.docx#3.2", "doc_name": "02_Положение_ДЗ.docx",
 "side": "before", "page": null, "clause": "3.2", "section": "3. Функции",
 "text": "Организация и проведение закупок ТРУ ..."}
```
- `side`: `"before"` | `"after"`
- `page`: номер страницы для PDF, `null` для docx/xlsx
- `clause`: номер пункта (`"3.2"`), для строк Excel — `"row:7"`

## Unit — подразделение (выход extract.py)
```json
{"unit_id": "after:ДЗЛ", "side": "after", "code": "ДЗЛ", "name": "Департамент закупок и логистики",
 "parent": "Заместитель Председателя Правления по экономике и финансам",
 "source": {"chunk_id": "...", "quote": "..."}}
```

## Function — функция подразделения (выход extract.py)
```json
{"func_id": "after:ДЗЛ:3.2", "unit_id": "after:ДЗЛ", "text": "Организация и проведение закупок ТРУ ...",
 "action_type": "execution",
 "source": {"chunk_id": "after/03_Положение_ДЗЛ.docx#3.2", "quote": "Организация и проведение закупок ТРУ"}}
```
- `action_type`: `execution | control | approval | coordination | accounting | acceptance | methodology | reporting | other`

## UnitMap — сопоставление подразделений (выход match_units.py)
```json
{"before_ids": ["before:ДЗ", "before:ДЛ"], "after_ids": ["after:ДЗЛ"],
 "status": "merged", "rationale": "...", "evidence": [Evidence]}
```
- `status`: `kept | renamed | merged | split | abolished | created | modified`

## FunctionMap — судьба функции «до» (выход match_functions.py)
```json
{"func_id": "before:ДЛ:3.4", "status": "lost", "matched_func_ids": [], "score": 0.41, "rationale": "..."}
```
- `status`: `covered | partial | lost`

## Evidence — ссылка на источник
```json
{"doc_name": "03_Положение_ДЛ.docx", "side": "before", "clause": "3.4", "page": null,
 "quote": "Проведение ежегодной инвентаризации складских запасов"}
```
`quote` — ДОСЛОВНЫЙ фрагмент из chunk.text. Верификатор проверяет это fuzzy-поиском.

## Finding — вывод агента
```json
{"finding_id": "F1", "type": "loss", "severity": "high",
 "title": "Потеряна функция инвентаризации складских запасов",
 "description": "...", "evidence": [Evidence], "recommendation": "...", "verified": true}
```
- `type`: `loss | duplicate | conflict`
- `severity`: `high | medium | low`

## Report — итог (выход run.py, вход app.py)
```json
{"meta": {"created_at": "...", "before_docs": [], "after_docs": [], "models": {}},
 "units": [Unit], "functions": [Function], "unit_map": [UnitMap],
 "function_map": [FunctionMap], "findings": [Finding], "rejected_findings": [Finding],
 "summary": "Итоговое заключение markdown", "log": ["Шаг 1/7: ..."]}
```
