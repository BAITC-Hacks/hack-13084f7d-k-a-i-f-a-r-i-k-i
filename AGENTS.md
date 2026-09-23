# AGENTS.md — OrgDiff Agent

ИИ-агент «Анализ организационной структуры и функционала» (кейс HackAlem AI).
Этот файл — единый источник правды для Codex: архитектура, модели данных, спецификации модулей, порядок задач и критерии готовности.
**Перед любой задачей прочитай этот файл целиком. Не отклоняйся от описанных интерфейсов без явного указания.**

---

## 0. Правила для Codex (обязательно)

1. Язык кода, идентификаторов, коммитов — английский. Тексты UI, промпты, отчёты — русский.
2. Python 3.11+, строгая типизация (type hints везде), Pydantic v2 для всех структур данных.
3. **Никакого хардкода под тестовый датасет.** Нельзя упоминать в коде коды подразделений (ДЗЛ, ОДР, …), названия файлов или номера пунктов из `data/demo/`. На защите будет *другой* контрольный комплект. Тестовый датасет используется только в `tests/` и `eval/`.
4. Все вызовы LLM — только через `orgagent/llm/client.py` (кэш, ретраи, structured output). Прямой `import openai` в других модулях запрещён.
5. Любой вывод (finding) обязан ссылаться на `fragment_id` существующих фрагментов. Текст цитаты берётся из фрагмента, **не генерируется LLM**.
6. Каждый этап пайплайна сохраняет артефакт в `runs/<run_id>/<stage>.json`. Этапы должны быть перезапускаемы по отдельности.
7. Ключи только из `.env`. `.env` в `.gitignore`, в репо — `.env.example`.
8. Каждая задача из раздела 12 закрывается только при зелёных тестах (`pytest -q`) и выполненных acceptance-критериях.
9. Не добавляй зависимости вне раздела 3 без необходимости; если добавляешь — впиши в `pyproject.toml` и объясни в PR-описании.

---

## 1. Суть задачи

Вход: два комплекта документов — «до» и «после» реорганизации (Word, PDF, Excel): оргструктуры, положения о подразделениях, распорядительные документы (приказы) с приложениями.

Выход:
- перечень подразделений со статусом: сохранено / изменено / объединено / разделено / переименовано / создано / упразднено;
- таблица сопоставления функций «до → после» (куда ушла каждая функция);
- потери функций, дублирования, конфликты интересов;
- для каждого вывода — документ + пункт + точная цитата;
- итоговое аналитическое заключение + рекомендации; экспорт в DOCX.

Ключевой принцип: **детерминированный пайплайн + LLM на узких проверяемых шагах** (извлечение по схеме, судья «покрыто / не покрыто», классификация ролей). Не свободный ReAct-агент. Агентный слой — оркестрация LangGraph, human-in-the-loop и чат-агент с инструментами поверх результатов.

---

## 2. Что известно о данных (из тестового комплекта)

Проверено на `data/demo/` (АО «КазЭнергоСеть», синтетика):

- **DOCX**: нумерация пунктов хранится *литеральным текстом* («3.9. Контроль …»), стиль `Normal`, таблиц нет. Но парсер ОБЯЗАН также поддерживать автонумерацию Word (`w:numPr`) — в контрольном комплекте она может быть.
- **PDF**: есть текстовый слой (шрифты встроены), по 1 странице. **Пункты переносятся на несколько строк** («3.2. Оценка эффективности … управления\nрисками.») → нужно склеивать строки до следующего номера пункта. OCR — fallback, если `pdffonts` пуст.
- **XLSX**: оргструктура — 1 лист; строки-заголовки над таблицей («Организационная структура …», «Приложение к приказу от … № …»); колонки: `№ | Код | Структурное подразделение | Непосредственное подчинение | Руководитель | Штатная численность`; последняя строка «Итого». Заголовок таблицы искать по ключевым словам, не по индексу строки.
- **Положение** имеет разделы: `1. Общие положения`, `2. Основная задача`, `3. Функции`, `4. Права`, `5. Ответственность`. Функции = подпункты раздела, заголовок которого содержит «Функци» (плюс «Задач» как вторичный источник). Код подразделения извлекается из «(далее – XXX)» в п. 1.1.
- **Приказ** — пункты верхнего уровня «1.», «2.», … (объединить, упразднить, переименовать, создать, утвердить в новой редакции, сохраняют действие без изменений, передать функции …).
- Название подразделения в заголовке положения стоит в предложном падеже («о Департаменте закупок») — сопоставлять по коду, затем fuzzy, затем LLM.

Эталон `ground_truth.json` (формат для eval): `unit_changes`, `function_losses`, `function_transfers_ok`, `partial_or_borderline`, `duplications`, `not_duplications` (ловушки), `conflicts_of_interest`, `conflicts_optional`. Сопоставление по `doc` (имя файла) + `clause` (например `"3.4"` или `"п. 1"`).

Известные ловушки (решать общими правилами в промптах, не хардкодом):
- одинаковое действие над **разными объектами** ≠ дубль («анализ рынка сбыта» vs «анализ рынка поставщиков»);
- похожий объект, **другое действие** ≠ покрытие («учёт складских остатков» не покрывает «инвентаризацию складских запасов»);
- общее слово ≠ покрытие («ведение реестра рисков / реестра поставщиков» не покрывает «ведение реестра договоров»);
- «разработка политики + контроль её соблюдения» в одном пункте — не конфликт интересов; «планирование бюджета + контроль исполнения бюджета» в финансовом подразделении — не конфликт.

---

## 3. Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.11 |
| Модели данных | Pydantic v2 |
| LLM | OpenAI API (Responses API, structured outputs через Pydantic) |
| Эмбеддинги | OpenAI `text-embedding-3-large` (настраивается) |
| Оркестрация | LangGraph (StateGraph + interrupt для HITL + чекпоинтер SQLite) |
| Парсинг | `python-docx`, `PyMuPDF` (fitz), `openpyxl`, `pytesseract` (fallback OCR), `rapidfuzz` |
| Векторный поиск | `numpy` (косинус в памяти; объём маленький — FAISS не нужен) |
| Кэш LLM | `diskcache` |
| UI | Streamlit + Plotly (Sankey) |
| API (опционально) | FastAPI |
| Отчёт | `python-docx` + Jinja2 (Markdown) |
| CLI | Typer |
| Тесты | pytest |
| Контейнеризация | Docker + docker-compose |

Модели задаются через `.env` (не хардкодить):
```
OPENAI_API_KEY=
OPENAI_MODEL_JUDGE=gpt-5-mini        # судья покрытия/дублей/конфликтов — заменить на актуальную модель аккаунта
OPENAI_MODEL_EXTRACT=gpt-5-mini      # извлечение из приказов, атомизация, роли
OPENAI_MODEL_REPORT=gpt-5            # итоговое заключение и чат
OPENAI_EMBED_MODEL=text-embedding-3-large
OPENAI_BASE_URL=                     # пусто = OpenAI; можно указать любой OpenAI-совместимый endpoint
LLM_CACHE_DIR=.cache/llm
```

---

## 4. Структура репозитория

```
orgdiff-agent/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── config/
│   ├── settings.yaml            # пороги, top-k, флаги этапов
│   └── sod_rules.yaml           # правила несовместимых ролей (конфликт интересов)
├── orgagent/
│   ├── __init__.py
│   ├── models.py                # ВСЕ Pydantic-модели (раздел 5)
│   ├── config.py                # загрузка .env + settings.yaml
│   ├── ingest/
│   │   ├── __init__.py          # ingest_folder(path, side) -> list[Document]
│   │   ├── docx_parser.py
│   │   ├── pdf_parser.py
│   │   ├── xlsx_parser.py
│   │   ├── clauses.py           # общая логика: номер пункта, склейка строк, разделы
│   │   └── classify.py          # тип документа: org_structure | regulation | order | job_description | other
│   ├── llm/
│   │   ├── client.py            # parse(schema, system, user, model) + embed(texts); кэш, ретраи
│   │   └── prompts/             # *.md шаблоны промптов (раздел 8)
│   ├── units/
│   │   ├── extract.py           # Unit из оргструктур и положений
│   │   ├── order.py             # OrderAction из приказов (LLM)
│   │   └── reconcile.py         # UnitChange: приказ + дифф оргструктур + дифф функций
│   ├── functions/
│   │   ├── extract.py           # Function из раздела «Функции»
│   │   ├── atomize.py           # разбиение составных пунктов (LLM)
│   │   └── tag.py               # домен + тип роли (LLM)
│   ├── analysis/
│   │   ├── retrieval.py         # эмбеддинги + top-k кандидатов
│   │   ├── coverage.py          # потери / переносы / частичное покрытие
│   │   ├── duplication.py       # дублирования
│   │   ├── conflicts.py         # конфликты интересов (SoD)
│   │   └── recommend.py         # рекомендации (опционально)
│   ├── verify/
│   │   └── evidence.py          # проверка ссылок и цитат, отсев неподтверждённого
│   ├── report/
│   │   ├── build.py             # AnalysisReport: summary от LLM только по findings
│   │   ├── markdown.py
│   │   └── docx_export.py
│   ├── graph/
│   │   ├── state.py             # PipelineState
│   │   ├── nodes.py             # обёртки этапов
│   │   └── pipeline.py          # StateGraph + interrupt после reconcile
│   ├── chat/
│   │   └── agent.py             # чат-агент с инструментами над результатами run
│   ├── storage.py               # runs/<run_id>/*.json save/load
│   └── cli.py                   # typer: run, eval, report
├── ui/
│   └── app.py                   # Streamlit
├── api/
│   └── main.py                  # FastAPI (опционально)
├── eval/
│   ├── eval.py                  # сравнение с ground_truth.json
│   └── README.md
├── data/
│   └── demo/                    # тестовый комплект: before/, after/, ground_truth.json
├── runs/                        # артефакты прогонов (в .gitignore, кроме runs/demo_reference/)
└── tests/
    ├── test_ingest.py
    ├── test_units.py
    ├── test_functions.py
    ├── test_analysis.py
    ├── test_verify.py
    └── test_eval.py
```

---

## 5. Модели данных (`orgagent/models.py`)

Реализовать ровно эти модели (можно добавлять поля, нельзя переименовывать).

```python
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

Side = Literal["before", "after", "reference"]   # reference = нормативка/бенчмарк

class DocType(str, Enum):
    ORG_STRUCTURE = "org_structure"
    REGULATION = "regulation"          # положение о подразделении
    ORDER = "order"                    # приказ / распорядительный документ
    JOB_DESCRIPTION = "job_description"
    NORMATIVE = "normative"            # внешние требования
    OTHER = "other"

class Fragment(BaseModel):
    id: str                  # "{side}/{file_name}#{clause}" напр. "after/03_Положение_ДЗЛ.docx#3.9"; для xlsx: "#row:5"
    side: Side
    doc_name: str            # имя файла, как в ground_truth
    doc_type: DocType
    clause: str | None       # "3.9", "п. 1" для приказа нормализуется в "1"; None для заголовков
    section: str | None      # "3. Функции"
    page: int | None
    text: str                # полный текст пункта (склеенные строки), без номера
    raw_text: str            # как в документе, с номером

class Document(BaseModel):
    side: Side
    doc_name: str
    path: str
    doc_type: DocType
    title: str | None
    meta: dict[str, str] = {}          # номер/дата приказа, «Приложение N»
    fragments: list[Fragment]

class Unit(BaseModel):
    uid: str                 # "{side}:{code}"
    side: Side
    code: str | None         # "ДЗЛ"
    name: str                # "Департамент закупок и логистики"
    parent: str | None       # непосредственное подчинение
    head: str | None
    headcount: int | None
    regulation_doc: str | None         # doc_name положения
    source_fragment_ids: list[str]

class OrderActionType(str, Enum):
    MERGE = "merge"; SPLIT = "split"; RENAME = "rename"; CREATE = "create"
    ABOLISH = "abolish"; NEW_EDITION = "new_edition"; UNCHANGED = "unchanged"
    TRANSFER_FUNCTIONS = "transfer_functions"; APPROVE_STRUCTURE = "approve_structure"; OTHER = "other"

class OrderAction(BaseModel):
    fragment_id: str
    action: OrderActionType
    from_units: list[str] = []         # коды или названия как в тексте
    to_units: list[str] = []
    transferred_functions: list[str] = []   # формулировки функций, явно переданных приказом
    note: str | None = None

class UnitChangeStatus(str, Enum):
    MERGED = "объединено"; SPLIT = "разделено"; RENAMED = "переименовано"
    CREATED = "создано"; ABOLISHED = "упразднено"
    MODIFIED = "изменено"; UNCHANGED = "сохранено без изменений"

class UnitChange(BaseModel):
    id: str                            # "UC1"
    status: UnitChangeStatus
    before_uids: list[str]
    after_uids: list[str]
    evidence: list[str]                # fragment_ids (пункт приказа, строки оргструктур)
    basis: Literal["order", "structure_diff", "function_diff", "llm"]
    confirmed_by_user: bool = False
    warnings: list[str] = []           # напр. «изменение не подтверждено приказом»

class RoleType(str, Enum):
    PLANNING = "planning"; EXECUTION = "execution"; PROCUREMENT = "procurement"
    ACCEPTANCE = "acceptance"; STORAGE_ACCOUNTING = "storage_accounting"; INVENTORY = "inventory"
    COMPLIANCE_CONTROL = "compliance_control"; AUDIT = "audit"; APPROVAL = "approval"
    POLICY_DEVELOPMENT = "policy_development"; MONITORING = "monitoring"
    REPORTING = "reporting"; METHODOLOGY = "methodology"; SUPPORT = "support"; OTHER = "other"

class Function(BaseModel):
    fid: str                           # "{fragment_id}" или "{fragment_id}.a" для атомов
    side: Side
    unit_uid: str
    fragment_id: str
    text: str                          # атомарная формулировка (для атомов — нормализованная LLM)
    source_quote: str                  # ТОЧНЫЙ текст пункта из фрагмента
    action: str | None = None          # «проведение»
    object: str | None = None          # «инвентаризация складских запасов»
    domain: str | None = None          # «склад», «закупки», «ИБ», «договоры», …
    role: RoleType | None = None

class CoverageVerdict(str, Enum):
    COVERED = "covered"; PARTIAL = "partial"; NOT_COVERED = "not_covered"

class FunctionMapping(BaseModel):
    before_fid: str
    verdict: CoverageVerdict
    after_fids: list[str]              # куда перешла (может быть несколько)
    same_unit_lineage: bool            # перешла в «наследника» или в другое подразделение
    mentioned_in_order: bool           # явно передана приказом
    rationale: str
    confidence: float = Field(ge=0, le=1)
    method: Literal["exact", "llm"]

class FindingType(str, Enum):
    LOSS = "loss"; PARTIAL_LOSS = "partial_loss"; DUPLICATION = "duplication"
    OVERLAP = "overlap"; CONFLICT = "conflict_of_interest"; TRANSFER = "transfer"
    UNIT_CHANGE = "unit_change"; INCONSISTENCY = "inconsistency"; COMPLIANCE_GAP = "compliance_gap"

class Severity(str, Enum):
    HIGH = "high"; MEDIUM = "medium"; LOW = "low"; INFO = "info"

class Evidence(BaseModel):
    fragment_id: str
    doc_name: str
    side: Side
    clause: str | None
    quote: str                         # копия Fragment.text, не генерируется

class Finding(BaseModel):
    id: str                            # "L1", "D1", "C1", "T1", "U1", ...
    type: FindingType
    severity: Severity
    title: str                         # коротко, по-русски
    explanation: str                   # 1–3 предложения, почему это отклонение
    units: list[str]                   # unit_uids
    function_ids: list[str]
    evidence: list[Evidence]           # минимум 1
    confidence: float = Field(ge=0, le=1)
    introduced_by_reorg: bool | None = None   # появилось ли в результате реорганизации
    recommendation: str | None = None
    verified: bool = False             # выставляет verify/evidence.py

class AnalysisReport(BaseModel):
    run_id: str
    unit_changes: list[UnitChange]
    mappings: list[FunctionMapping]
    findings: list[Finding]
    summary_md: str                    # заключение, каждое утверждение с [ID] ссылкой
    stats: dict[str, int]
    disclaimer: str = ("Выводы носят рекомендательный характер и требуют проверки "
                       "ответственным сотрудником.")
```

---

## 6. Архитектура пайплайна

```
 before/ + after/ (+ reference/ опционально)
        │
 [N1] ingest ──────────── Document[], Fragment[]              (детерминированно)
        │
 [N2] extract_units ───── Unit[] (оргструктуры + положения)   (детерминированно + fuzzy)
        │
 [N3] parse_orders ────── OrderAction[]                       (LLM, structured output)
        │
 [N4] reconcile_units ─── UnitChange[]                         (правила + LLM для спорных)
        │
 ⏸  INTERRUPT: пользователь подтверждает/правит UnitChange в UI (в CLI — флаг --auto-approve)
        │
 [N5] extract_functions ─ Function[] (раздел «Функции»)       (детерминированно)
 [N6] atomize_and_tag ─── Function[] атомы + domain + role     (LLM, batch по подразделению)
 [N7] embed ───────────── векторы функций                      (OpenAI embeddings, кэш)
        │
        ├── [N8]  coverage ───── FunctionMapping[] → LOSS / PARTIAL_LOSS / TRANSFER
        ├── [N9]  duplication ── DUPLICATION / OVERLAP
        └── [N10] conflicts ──── CONFLICT (SoD-правила + LLM-подтверждение)
        │
 [N11] verify_evidence ── отсев/маркировка неподтверждённого
 [N12] recommend ──────── рекомендации к findings (опционально, LLM)
 [N13] build_report ───── AnalysisReport + summary_md + DOCX
```

- Реализация: `langgraph.StateGraph(PipelineState)`, узлы — тонкие обёртки над функциями модулей. Чекпоинтер — `SqliteSaver` в `runs/checkpoints.sqlite`.
- `interrupt()` после N4. UI показывает таблицу UnitChange, пользователь правит и жмёт «Продолжить» → `Command(resume=edited_changes)`.
- Каждый узел пишет `runs/<run_id>/<node>.json`. Функции модулей должны работать и без LangGraph (для тестов и CLI).
- N8/N9/N10 независимы — можно запускать параллельно (fan-out в графе).

`PipelineState` (`graph/state.py`): `run_id, before_dir, after_dir, reference_dir | None, documents, units, order_actions, unit_changes, functions, mappings, findings, report, errors: list[str]`.

---

## 7. Спецификации модулей

### 7.1 `ingest/`

`clauses.py` — общая логика:
- регэкс номера пункта в начале строки: `^\s*(\d+(?:\.\d+)*)\.?\s+(.+)` (поддержать «3.10.», «п. 1», «1)»);
- **склейка**: строка без номера пункта присоединяется к предыдущему пункту (через пробел); пустые строки и колонтитулы («Страница N», повторяющиеся шапки) отбрасываются;
- определение раздела: пункт верхнего уровня (`\d+\.` + короткий текст без точки в конце, напр. «3. Функции») → `section` для последующих подпунктов;
- нормализация номера: без завершающей точки и префикса «п.» (`"3.9"`, `"1"`).

`docx_parser.py`:
- обход `document.element.body` по порядку (параграфы и таблицы);
- если у параграфа есть `w:numPr` — вычислить номер по `numbering.xml` (счётчики по `numId/ilvl`), иначе взять из текста;
- таблицы: каждая строка → фрагмент `#table{t}:row{r}`.

`pdf_parser.py`:
- `fitz`: текст по страницам; если текста < 50 символов на странице → OCR (`pytesseract`, `lang="rus+kaz+eng"`);
- дальше — общий `clauses.py`; `page` проставляется.

`xlsx_parser.py`:
- найти строку заголовка таблицы (содержит ≥2 из: «код», «подразделени», «подчинени», «численност»); сопоставить колонки по ключевым словам (fallback — LLM-маппинг колонок);
- строки над заголовком → `Document.meta` (напр. `"order_ref": "Приложение к приказу от 15.01.2026 № 45-п"`);
- каждая строка данных → Fragment `#row:{n}`, `clause=None`, `text` = «Код | Название | Подчинение | …»; строки «Итого»/пустые — пропустить.

`classify.py` — тип документа: правила по содержимому (xlsx с колонкой «Код/Подразделение» → ORG_STRUCTURE; «ПОЛОЖЕНИЕ» + «Функции» → REGULATION; «ПРИКАЗ»/«ПРИКАЗЫВАЮ» → ORDER; «должностная инструкция» → JOB_DESCRIPTION); если правила не сработали — LLM-классификатор. Имя файла — только как слабый сигнал.

**Acceptance (T2):** на `data/demo`:
- `after/03_Положение_ДЗЛ.docx` → 11 фрагментов в разделе «Функции» с clause `3.1…3.11`;
- `before/08_Положение_СВА.pdf` → пункт `3.2` одной строкой, заканчивается «управления рисками.»;
- `after/01_Приказ_45-п_о_реорганизации.pdf` → пункты `1…9`, тип ORDER;
- обе оргструктуры → 9 и 8 строк данных, тип ORG_STRUCTURE.

### 7.2 `units/`

`extract.py`:
- из ORG_STRUCTURE: Unit на каждую строку (code, name, parent, head, headcount);
- из REGULATION: код из «(далее – XXX)», название из заголовка/п. 1.1, подчинение из п. 1.2; привязка к Unit той же стороны по коду → иначе `rapidfuzz` по названию (порог 85, с лемматизацией-лайт: отбросить окончания/предлоги «о», «об») → иначе LLM; `regulation_doc` = имя файла.
- положение без Unit в оргструктуре → создаётся Unit с warning.

`order.py`:
- для каждого ORDER-документа: все пункты в одном LLM-вызове → `list[OrderAction]` (схема `OrderActionsOut`); промпт `prompts/order_actions.md`;
- `fragment_id` действия обязан быть одним из переданных id (валидация, иначе ретрай).

`reconcile.py` — сборка `UnitChange` в порядке приоритета:
1. явные действия приказа (MERGE/RENAME/CREATE/ABOLISH/SPLIT/NEW_EDITION/UNCHANGED) → статус; разрешение `from_units/to_units` в uid через код → fuzzy по названию;
2. дифф оргструктур по кодам для подразделений, не упомянутых в приказе: код есть в обеих → сравнить наборы функций (exact-normalized): совпадают → UNCHANGED, иначе MODIFIED; код только «до» → ABOLISHED с warning «не подтверждено приказом»; только «после» → CREATED с warning;
3. согласованность: если приказ говорит UNCHANGED, а функции отличаются → Finding INCONSISTENCY; если приказ говорит NEW_EDITION, а функции идентичны → info;
4. изменение штатной численности → в `warnings` (информативно).

**Acceptance (T4):** на demo: ДЗ+ДЛ→ДЗЛ merged (evidence = пункт 1 приказа); ОДР abolished (п.2); ДИТ→ДЦТ renamed (п.3); ДУР created (п.4); ЮД, КД, СВА modified (п.5); СБ, ФД unchanged (п.7).

### 7.3 `functions/`

`extract.py`: Function на каждый фрагмент REGULATION/JOB_DESCRIPTION из раздела, заголовок которого содержит «функци» (fallback: «задач», «обязанност»). `source_quote = fragment.text`.

`atomize.py` (LLM, один вызов на подразделение): если пункт содержит несколько самостоятельных функций (разные действия/объекты) — разбить на атомы `fid = fragment_id + ".a"/".b"`, `text` — нормализованная формулировка, `source_quote` — исходный пункт целиком. Иначе оставить как есть. Также заполняет `action` и `object`.

`tag.py` (LLM, тот же вызов, что atomize — одна схема): `domain` (свободная строка, но из рекомендованного списка в промпте: закупки, логистика, склад, договоры, правовое, ИТ, ИБ, безопасность, финансы, бюджет, учёт, аудит, риски, коммерция, HR, корпоративное управление, прочее) и `role: RoleType`.

**Acceptance (T5):** ДЗЛ 3.7 разбит минимум на 2 атома (хранение/учёт и списание); ДЛ 3.4 имеет role=`inventory`, domain=`склад`; ДЗЛ 3.9 role=`compliance_control`, domain=`закупки`; ДЗЛ 3.2 role=`procurement`.

### 7.4 `analysis/retrieval.py`

- `embed_functions(functions)` — эмбеддинг строки `f"{unit.name}: {function.text}"` и отдельно `function.text`; хранить оба;
- `top_k(query_fid, candidate_fids, k)` — косинус по `function.text`.

### 7.5 `analysis/coverage.py` — потери функций

Для каждой функции «до» (всех подразделений, не только изменённых):
1. **exact**: нормализованный текст (lower, ё→е, без пунктуации и «Общества») совпадает с функцией «после» → `COVERED`, method=exact, без LLM;
2. иначе top-k (k=6) кандидатов среди **всех** функций «после» + кандидаты из «наследников» по UnitChange;
3. **LLM-судья** (`prompts/coverage_judge.md`) — один вызов на функцию: вход — функция «до», её подразделение, статус подразделения, связанные пункты приказа (TRANSFER_FUNCTIONS), список кандидатов с id; выход `CoverageOut{verdict, after_fids, rationale, confidence}`; `after_fids` валидировать ⊂ переданных id.

Правила судьи (в промпте): покрытие = то же действие над тем же объектом (синонимы допустимы); другое действие над похожим объектом — не покрытие; общее слово («реестр», «контроль», «анализ») при разных объектах — не покрытие; частичное — кандидат покрывает только часть объёма или обобщённо.

Findings:
- `NOT_COVERED` → `LOSS` (severity HIGH, если подразделение упразднено/объединено; иначе MEDIUM), evidence = пункт «до» + пункт приказа о реорганизации подразделения (если есть);
- `PARTIAL` → `PARTIAL_LOSS` (MEDIUM/LOW), evidence = пункт «до» + пункты-кандидаты «после»;
- `COVERED` в **другом** подразделении (не наследник) → `TRANSFER` (INFO), evidence = оба пункта (+ пункт приказа, если перенос упомянут).

`FunctionMapping` сохраняется для всех — это таблица сопоставления функций в UI.

### 7.6 `analysis/duplication.py`

1. пары функций «после» из **разных** подразделений; кандидаты — косинус ≥ `dup_threshold` (стартово 0.55, тюнить на eval) ИЛИ совпадение `domain` + пересечение ключевых лемм объекта; не более `max_pairs_per_function` = 5;
2. LLM-судья (`prompts/duplication_judge.md`), батч до 10 пар за вызов: `DUPLICATION` (то же действие над тем же объектом) / `OVERLAP` (пересечение зон ответственности) / `DISTINCT` (+ rationale);
3. `introduced_by_reorg`: true, если хотя бы одна из функций не имеет `COVERED`-предка в том же подразделении-предшественнике (т.е. появилась при реорганизации); дубли, существовавшие до реорганизации, помечаются `false` и получают severity ниже.

Правила судьи: различать объект полностью («рынок сбыта/конкурентная среда» ≠ «рынок поставщиков»); «разработка политики X» в двух подразделениях = дубль, даже если у одного есть ещё «контроль соблюдения»; дубль — только если оба пункта *исполняют* функцию, а не «участвуют/согласуют».

### 7.7 `analysis/conflicts.py` — конфликт интересов (SoD)

Два механизма, результаты объединяются:

**A. Правила ролей** (`config/sod_rules.yaml`), внутри одного подразделения «после», по функциям из **разных пунктов**:
```yaml
rules:
  - id: SOD_PROC_CONTROL
    roles: [procurement, compliance_control]
    same_domain: true
    title: "Исполнение и контроль одного процесса в одном подразделении"
  - id: SOD_PROC_ACCEPT
    roles: [procurement, acceptance]
    same_domain: false
    domains_any: [[закупки], [склад, логистика]]
    title: "Закупка и приёмка ТМЦ в одном подразделении"
  - id: SOD_EXEC_AUDIT
    roles: [execution, audit]
    same_domain: true
    title: "Исполнение и аудит одного процесса"
  - id: SOD_ACCOUNT_INVENTORY
    roles: [storage_accounting, inventory]
    same_domain: true
    title: "Учёт ТМЦ и их инвентаризация"
  - id: SOD_APPROVE_EXEC
    roles: [approval, execution]
    same_domain: true
    title: "Утверждение и исполнение в одном подразделении"
exclusions:
  - "planning + monitoring одного бюджета/плана — не конфликт"
  - "policy_development + compliance_control в одном пункте — не конфликт"
```
**B. Потеря независимости контроля**: функция с role `compliance_control`/`audit`, которая «до» была в подразделении с подчинением Совету директоров/комитету (или role audit), а «после» — в операционном подразделении, исполняющем тот же процесс → кандидат с усиленной severity (HIGH).

Каждый кандидат → LLM-подтверждение (`prompts/conflict_judge.md`): `is_conflict, explanation, severity`. Evidence = оба пункта + (для B) пункт «до» из независимого подразделения.

### 7.8 `verify/evidence.py`

Для каждого Finding:
- все `fragment_id` существуют; `Evidence.quote == Fragment.text` (после нормализации пробелов) — иначе quote переписывается из фрагмента;
- `function_ids` существуют и их `fragment_id` входят в evidence;
- Finding без валидного evidence → удаляется, в `errors` пишется причина;
- `verified=True`.

Для `summary_md` (после N13): регэкс по ссылкам `[L1]`, `[D2]`, … — все ID должны существовать; упоминания «п. X.Y» должны встречаться в evidence соответствующих findings; нарушения → перегенерация (макс. 2 раза), затем fallback на шаблонное заключение без LLM.

### 7.9 `report/`

- `build.py`: LLM получает **только** JSON (unit_changes + findings без fragments) и пишет заключение по структуре: 1) что изменилось в структуре; 2) ключевые риски (потери, дубли, конфликты) со ссылками `[ID]`; 3) рекомендации; 4) дисклеймер. Промпт `prompts/report.md` запрещает факты вне JSON.
- `markdown.py`: Jinja2-шаблон: заключение + таблица подразделений + таблица сопоставления функций + карточки findings с цитатами.
- `docx_export.py`: тот же контент в DOCX (таблицы, цитаты курсивом, ссылки «документ, п. X»).

### 7.10 `chat/agent.py`

LangGraph ReAct-агент (или OpenAI tool calling) над готовым run. Инструменты:
`list_unit_changes()`, `list_findings(type=None)`, `get_finding(id)`, `get_fragment(fragment_id)`, `search_functions(query, side=None)`, `get_mapping(before_fid)`.
Системный промпт: отвечать только по результатам инструментов, каждое утверждение с `fragment_id`/ID вывода; если данных нет — так и сказать.

### 7.11 Опционально (после must have)

- **Нормативка** (`side="reference"`, `DocType.NORMATIVE`): требования = пункты документа; для каждого требования top-k функций «после» + судья → `COMPLIANCE_GAP` для непокрытых требований.
- **Бенчмаркинг**: `data/benchmarks/*.yaml` (подразделения других операторов из открытых источников: название → нормализованный тип функции); сравнение таксономии типов подразделений → таблица «есть у нас / есть у других».
- **Рекомендации** (`recommend.py`): для LOSS — предложить подразделение-кандидата по близости domain; для DUPLICATION — закрепить за одним с обоснованием; для CONFLICT — вернуть контроль в независимое подразделение.

---

## 8. Промпты (`orgagent/llm/prompts/*.md`)

Общие правила для всех промптов:
- системная часть на русском, роль: «аналитик по организационному проектированию»;
- вход — JSON с id; выход — строго Pydantic-схема (structured output);
- «Используй только предоставленный текст. Не придумывай функции, пункты и документы. Если данных недостаточно — выбери консервативный вариант и снизь confidence.»;
- в каждом судье 3–5 few-shot примеров **на вымышленной другой предметной области** (не из demo), покрывающих ловушки из раздела 2;
- температура 0 (если модель поддерживает; параметр в `settings.yaml`), фиксированный seed где доступно.

Файлы: `order_actions.md`, `atomize_tag.md`, `unit_match.md`, `coverage_judge.md`, `duplication_judge.md`, `conflict_judge.md`, `report.md`, `chat_system.md`, `doc_classify.md`.

---

## 9. LLM-клиент (`orgagent/llm/client.py`)

```python
class LLMClient:
    def parse(self, schema: type[BaseModel], system: str, user: str,
              model: str | None = None, max_retries: int = 2) -> BaseModel: ...
    def embed(self, texts: list[str]) -> np.ndarray: ...
```
- OpenAI Responses API: `client.responses.parse(model=..., input=[...], text_format=schema)`;
- кэш `diskcache`: ключ = sha256(model + system + user + schema JSON-schema); для эмбеддингов — sha256(model + text);
- ретраи с экспоненциальной задержкой на 429/5xx; при ошибке валидации — повтор с сообщением об ошибке в input;
- счётчик токенов и стоимости → `runs/<run_id>/usage.json`;
- `OPENAI_BASE_URL` поддерживается (любой OpenAI-совместимый провайдер / локальная модель).

---

## 10. Интерфейсы

### CLI (`orgagent/cli.py`, Typer)
```
orgagent run --before data/demo/before --after data/demo/after [--reference DIR] [--auto-approve] [--run-id ID]
orgagent report --run-id ID --format md|docx
orgagent eval --run-id ID --gt data/demo/ground_truth.json
```

### Streamlit (`ui/app.py`) — вкладки
1. **Загрузка**: два file_uploader (до/после, multiple), кнопка «Демо-комплект», кнопка «Запустить».
2. **Подразделения**: `st.data_editor` с UnitChange (статус редактируемый) + Sankey «до → после» (Plotly; ширина потока = число функций) + кнопка «Подтвердить и продолжить» (resume графа).
3. **Функции**: таблица FunctionMapping (функция до → функция после, вердикт, цветовая маркировка), фильтры по подразделению и вердикту.
4. **Отклонения**: карточки Finding (тип, severity, объяснение, цитаты с документом и пунктом; раскрывающийся просмотр полного документа с подсветкой фрагмента), фильтр по типу.
5. **Заключение**: summary_md + кнопки «Скачать DOCX» / «Скачать MD».
6. **Чат**: вопросы по результатам.
Сайдбар: run_id, статистика, стоимость прогона, дисклеймер.

---

## 11. Оценка качества (`eval/eval.py`)

- Вход: `runs/<run_id>/report.json` + `ground_truth.json`.
- Сопоставление по `(doc_name, clause)`; clause приказа нормализовать («п. 1» → «1»).
- Метрики:
  - unit_changes: accuracy по статусам (сопоставление по множествам кодов);
  - losses / duplications / conflicts: TP, FP, FN, precision, recall (дубль совпал, если совпала неупорядоченная пара пунктов; конфликт — пара пунктов);
  - `not_duplications` — любой найденный дубль по этой паре = ошибка «trap_hit»;
  - `partial_or_borderline` — не штрафуется ни как TP, ни как FP;
  - `conflicts_optional` — считается как бонус, не FP;
  - source_accuracy: доля findings, у которых все evidence ссылаются на существующие пункты.
- Вывод: таблица в консоль + `eval/results.json`; результаты вставить в README.
- **Цель на demo:** потери 2/2, дубли 2/2, конфликты 1/1 (+ бонус), 0 trap_hit, FP ≤ 1.

---

## 12. Порядок задач для Codex

Выполнять строго последовательно; каждая задача — отдельная ветка/PR с тестами.

| # | Задача | Готово, когда |
|---|---|---|
| T0 | Скелет репо (раздел 4), `pyproject.toml`, `.env.example`, `config.py`, `settings.yaml`, pytest, ruff; копия датасета в `data/demo/` | `pytest` запускается, `orgagent --help` работает |
| T1 | `models.py` целиком (раздел 5) + `storage.py` | тесты сериализации туда-обратно всех моделей |
| T2 | `ingest/` (7.1) | acceptance T2 из 7.1 зелёные |
| T3 | `llm/client.py` (раздел 9) с кэшем | тест с моком OpenAI; повторный вызов берётся из кэша |
| T4 | `units/` (7.2) | acceptance T4 зелёные (реальный API, помечено `@pytest.mark.llm`) |
| T5 | `functions/` (7.3) | acceptance T5 зелёные |
| T6 | `analysis/retrieval.py` + `coverage.py` (7.4–7.5) | на demo: L1 и L2 найдены; ОДР 3.2/3.5 → ЮД 3.4/3.5 TRANSFER; СВА 3.3 → ДЗЛ 3.9 TRANSFER |
| T7 | `duplication.py` (7.6) | D1, D2 найдены; пара КД 3.2 / ДЗЛ 3.3 = DISTINCT |
| T8 | `conflicts.py` + `sod_rules.yaml` (7.7) | C1 найден с severity HIGH; бонус (ДЗЛ 3.2/3.6) найден; нет конфликтов у СБ 3.2 и ФД 3.1 |
| T9 | `verify/` (7.8) | тест: finding с несуществующим fragment_id удаляется; подменённая цитата восстанавливается |
| T10 | `report/` (7.9) | MD и DOCX генерируются; в summary все `[ID]` валидны |
| T11 | `graph/` (раздел 6) + `cli.py` | `orgagent run --auto-approve` на demo проходит end-to-end, все артефакты в `runs/` |
| T12 | `eval/eval.py` (раздел 11) | вывод метрик; цель на demo достигнута |
| T13 | `ui/app.py` (раздел 10) с HITL | полный сценарий в браузере: загрузка → подтверждение → отклонения → DOCX |
| T14 | `chat/agent.py` (7.10) | ответ на «почему ДЗЛ 3.9 — конфликт?» со ссылками на пункты |
| T15 | Docker + docker-compose | `docker compose up` → UI на :8501, демо работает |
| T16 | README (раздел 13) + схема архитектуры (`docs/architecture.png` или Mermaid) | новый человек запускает по README за 5 минут |
| T17* | Опционально: нормативка, бенчмаркинг, рекомендации (7.11) | — |

После T12 — цикл тюнинга: менять только промпты и пороги в `settings.yaml`, каждое изменение подтверждать прогоном `eval`.

---

## 13. README (требования — это 25 баллов)

Разделы: 1) задача и что делает агент (3–4 предложения + скриншот UI); 2) архитектура (Mermaid-диаграмма пайплайна из раздела 6 + пояснение каждого узла); 3) как агент обеспечивает прослеживаемость и отсутствие галлюцинаций (verify, цитаты только из фрагментов, заключение только из findings); 4) стек; 5) быстрый старт: `cp .env.example .env` → ключ → `docker compose up` или `pip install -e . && orgagent run …`; 6) сценарий демо по шагам; 7) результаты eval на демо-комплекте (таблица метрик); 8) структура репозитория; 9) конфигурация (модели, пороги, SoD-правила); 10) ограничения и дальнейшее развитие (нормативка, бенчмаркинг, локальные модели для конфиденциальных документов, масштабирование на сотни положений).

---

## 14. Definition of Done (для сдачи)

- [ ] `docker compose up` → рабочий UI, демо-комплект грузится одной кнопкой
- [ ] Must have 1–5 из ТЗ закрыты и видны в UI
- [ ] У каждого вывода — документ, пункт, точная цитата
- [ ] Eval на demo: 2/2 потери, 2/2 дубля, 1/1 конфликт, 0 trap_hit
- [ ] Прогон на незнакомом комплекте не падает (проверить на вручную изменённой копии demo: переименовать коды, переставить файлы, добавить автонумерацию в docx)
- [ ] Экспорт заключения в DOCX
- [ ] README по разделу 13, метрики внутри
- [ ] В репо нет ключей; `.env.example` есть

---

## 15. Уточнения плана по аудиту T0

Добавлено после чтения полного тестового комплекта. Порядок T0–T17 и имена
интерфейсов сохранены. Архитектура документируется уже на T0 по запросу
пользователя; итоговые требования T16 проверяются после готовности приложения.

1. **N4 до N5:** для сравнения исходных функций N4 использует сигнатуры пунктов
   из `Document.fragments`. Общий helper определения функциональных разделов
   создаётся в T2 и затем используется N4/N5. Атомизация остаётся в N6.
2. **Приоритет приказа:** MERGE/SPLIT/RENAME/CREATE/ABOLISH определяют основной
   статус; NEW_EDITION/UNCHANGED не перезаписывают явное структурное действие.
   Сохранять все основания; несовместимые действия направлять на HITL.
3. **Барьер аналитики:** N8/N9/N10 могут параллельно находить кандидатов;
   `introduced_by_reorg`, коррекция severity и решения, зависящие от mappings,
   финализируются после N8. Findings объединять детерминированно, без повторного
   накопления при resume; каждой ветви — собственный артефакт.
4. **Источники и ID:** в T1–T2 уточнить детерминированные ID для пунктов без
   номера, повторяющихся номеров, нескольких листов и подразделений без кода.
   Обычные форматы из раздела 5 сохраняются. Коллизии не перезаписывать молча.
5. **Артефакты:** в T1 — атомарная запись JSON и версия схемы; в T11 — manifest
   хешей входов/настроек/промптов/моделей и инвалидация зависимых стадий. Ошибка
   этапа отличается от успешно полученного пустого результата. Секреты не
   сохраняются. Исходное согласование и подтверждённая редакция — разные файлы.
   `--auto-approve` не означает `confirmed_by_user=True`.
6. **Неполнота документов:** отсутствующее/непрочитанное положение не доказывает
   потери функций; фиксировать диагностику. Для предупреждений Unit использовать
   разрешённое дополнительное поле либо отдельный диагностический артефакт.
   Рабочее правило OCR — порог извлечённого текста из 7.1; `pdffonts` лишь
   вспомогательная диагностика. Подписи приказов не приклеивать к последнему
   пункту; «Утверждено приказом» в шапке положения не определяет тип ORDER.
7. **Доказательства заключения:** изменения структуры представлены также
   findings типа UNIT_CHANGE с ID `U…`. Верификатор восстанавливает из Fragment
   не только цитату, но и документ, сторону и пункт; после N13 проверяет ссылки.
8. **Подготовка demo:** содержимое исходного комплекта сохранять; в копии
   `data/demo/` восстанавливать повреждённые UTF-8/CP866 имена, проверяя коллизии
   и хеши. По явному запросу пользователя на T1 имена восстановлены также
   в `HackAlem_test_dataset/`; журнал — `eval/dataset_renames.json`.
   Код подготовки fixtures размещать в `eval/`, не в `orgagent/`.
9. **Eval:** нормализовать пояснения в статусах эталона, групповые записи и
   «п.» в clause; сопоставлять пары без учёта порядка. Несколько атомов одного
   пункта не дают несколько TP. Сам эталон не редактировать.
10. **T0 и зависимости:** конфигурационные модели допустимы в `models.py` уже
    на T0, предметные модели раздела 5 реализуются на T1. `python-dotenv` и
    `PyYAML` обслуживают предусмотренные форматы конфигурации; SQLite saver
    поставляется пакетом `langgraph-checkpoint-sqlite`. Базовые проверки работают
    без API-ключа; реальные LLM-тесты включаются явно через `--run-llm`.

Подробности: [docs/architecture.md](docs/architecture.md), фактическая проверка
датасета: [eval/dataset_audit.md](eval/dataset_audit.md).

## 16. Уточнения пользователя при переходе к T1

- Основной способ запуска **всего сервиса — Docker Compose**. Локальная Python
  среда остаётся инструментом разработки. На T1 готовится и проверяется
  контейнер для CLI/check и тестов; T15 закрывается только после рабочего
  UI, полного demo-прогона и постоянного хранения данных.
- Пошаговый статус ведётся в [PLAN.md](PLAN.md). После принятого и проверенного
  шага ставить `[Done]`; заглушки и непроверенные этапы так не отмечать.
- T1 сохраняет файлы этапов как обычный JSON модели/списка, чтобы `report.json`
  напрямую читался eval. Версия формата хранится в `runs/<run_id>/manifest.json`.
  Manifest с хешами входов и инвалидация стадий относятся к T11.
