"""Шаг 2. Извлечение подразделений и функций.   Владелец: роль 1.

Сейчас работает ЭВРИСТИКА (подходит для data/test_set): подразделение = документ-положение,
код берётся из «(далее – XX)», функции = пункты раздела «Функции».
TODO: extract_llm() — structured output, для документов произвольного вида;
      эвристику оставить как fallback и для оффлайн-тестов.
"""
import re
from collections import defaultdict
from .schemas import Chunk, Unit, Function

CODE_RE = re.compile(r"^(.+?)\s*\(далее\s*[–-]\s*([А-ЯЁA-Z]{2,6})\)")

EXTRACT_PROMPT = """Ты извлекаешь данные из положения о структурном подразделении.
Верни ТОЛЬКО JSON: {"unit": {"code", "name", "parent"}, "functions": [{"chunk_id", "text", "quote", "action_type"}]}.
Правила:
- функции бери только из пунктов, которые явно описывают функции/обязанности подразделения;
- quote — ДОСЛОВНЫЙ фрагмент из текста пункта (5–15 слов), без перефразирования;
- chunk_id — ровно тот, что указан у пункта во входных данных;
- action_type: execution|control|approval|coordination|accounting|acceptance|methodology|reporting|other.
Пункты документа:
{chunks}
"""

CONTROL_WORDS = ("контрол", "проверк", "аудит", "надзор")
ACTION_RULES = [("acceptance", ("приёмк", "приемк")), ("control", CONTROL_WORDS),
                ("approval", ("утвержд",)), ("accounting", ("учёт", "учет", "инвентариз")),
                ("reporting", ("отчёт", "отчет")), ("methodology", ("методич", "политик", "стратег")),
                ("coordination", ("взаимодейств", "согласов"))]


def guess_action_type(text: str) -> str:
    t = text.lower()
    for at, words in ACTION_RULES:
        if any(w in t for w in words):
            return at
    return "execution"


def extract_heuristic(chunks: list[Chunk]):
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[(c["side"], c["doc_name"])].append(c)
    units, functions = [], []
    for (side, doc), cs in by_doc.items():
        code_ch = next((c for c in cs if CODE_RE.match(c["text"])), None)
        if not code_ch:
            continue                                   # не положение (приказ, оргструктура)
        name, code = CODE_RE.match(code_ch["text"]).groups()
        parent_ch = next((c for c in cs if "подчинение" in c["text"].lower()), None)
        parent = parent_ch["text"].split(":", 1)[-1].split(".")[0].strip() if parent_ch else ""
        uid = f"{side}:{code}"
        units.append({"unit_id": uid, "side": side, "code": code, "name": name.strip(), "parent": parent,
                      "source": {"chunk_id": code_ch["chunk_id"], "quote": code_ch["text"][:120]}})
        for c in cs:
            if "функци" in c["section"].lower():
                functions.append({"func_id": f"{uid}:{c['clause']}", "unit_id": uid, "text": c["text"],
                                  "action_type": guess_action_type(c["text"]),
                                  "source": {"chunk_id": c["chunk_id"], "quote": c["text"]}})
    return units, functions


def extract_llm(chunks: list[Chunk]):
    """TODO роль 1: по документу — один вызов llm.openai_client.chat_json(EXTRACT_PROMPT...)."""
    raise NotImplementedError


def extract(chunks: list[Chunk], use_llm: bool = False):
    if use_llm:
        try:
            return extract_llm(chunks)
        except NotImplementedError:
            pass
    return extract_heuristic(chunks)
