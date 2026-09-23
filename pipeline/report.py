TYPE_RU = {"loss": "Потеря функции", "duplicate": "Дублирование", "conflict": "Конфликт интересов"}
STATUS_RU = {"kept": "сохранено", "renamed": "переименовано", "merged": "объединено", "split": "разделено",
             "abolished": "упразднено", "created": "создано", "modified": "изменено"}

DISCLAIMER = "_Выводы носят рекомендательный характер и требуют проверки ответственным сотрудником._"

LLM_PROMPT = (
    "Ты — эксперт по анализу организационных документов. "
    "На вход подаётся JSON со списком ПОДТВЕРЖДЁННЫХ отклонений. "
    "Сформируй краткое итоговое заключение на русском. "
    "НЕ выдумывай факты, которых нет во входных данных. Не ссылайся на документы, "
    "кроме указанных в evidence. Если findings пуст — так и напиши."
)


def _esc(s: str) -> str:
    """Экранирует markdown-спецсимволы и убирает переводы строк."""
    return (s or "").replace("\n", " ").replace("\\", "\\\\").translate(
        str.maketrans({c: "\\" + c for c in "*_`[]#"})
    )


def _verified(report: dict) -> list[dict]:
    """Findings, которые прошли верификацию (шаг 6)."""
    return [f for f in report["findings"] if f.get("status", "verified") in
            ("verified", "confirmed", "approved")]


def build_summary(report: dict) -> str:
    lines = ["## Итоговое заключение", "", DISCLAIMER, "",
             "### Изменения подразделений"]
    for m in report["unit_map"]:
        before = ", ".join(m["before_ids"]) or "—"
        after = ", ".join(m["after_ids"]) or "—"
        lines.append(f"- {before} → {after}: **{STATUS_RU.get(m['status'], m['status'])}**")

    lines += ["", "### Выявленные отклонения"]
    findings = _verified(report)
    if not findings:
        lines.append("Подтверждённых отклонений не выявлено.")
    for f in findings:
        src = "; ".join(f"{_esc(e['doc_name'])} п.{_esc(e['clause'])}" for e in f["evidence"]) or "—"
        lines.append(f"- **{TYPE_RU.get(f['type'], f['type'])}** ({f['severity']}): {_esc(f['title'])}. Источник: {src}")
    return "\n".join(lines)


def build_summary_llm(report: dict, llm) -> str:
    """llm(prompt: str) -> str. В промпт идут только verified findings."""
    import json
    findings = _verified(report)
    if not findings:
        return build_summary(report)
    payload = json.dumps(findings, ensure_ascii=False, indent=2)
    text = llm(f"{LLM_PROMPT}\n\nVerified findings:\n{payload}").strip()
    if not text:
        return build_summary(report)
    return f"## Итоговое заключение\n\n{DISCLAIMER}\n\n{text}"


def to_markdown(report: dict) -> str:
    md = [report["summary"], "", "### Подтверждающие цитаты"]
    for f in report["findings"]:
        md.append(f"**{_esc(f['finding_id'])}. {_esc(f['title'])}**")
        for e in f["evidence"]:
            md.append(f"> {_esc(e['quote'])}  \n> — {_esc(e['doc_name'])}, п. {_esc(e['clause'])}")
        if f.get("recommendation"):
            md.append(f"Рекомендация: {_esc(f['recommendation'])}")
        md.append("")
    return "\n".join(md)


def export_docx(report: dict, path: str) -> str:
    from docx import Document
    doc = Document()
    doc.add_heading("Итоговое заключение", level=1)
    doc.add_paragraph(DISCLAIMER.strip("_")).runs[0].italic = True

    doc.add_heading("Изменения подразделений", level=2)
    for m in report["unit_map"]:
        before = ", ".join(m["before_ids"]) or "—"
        after = ", ".join(m["after_ids"]) or "—"
        doc.add_paragraph(f"{before} → {after}: {STATUS_RU.get(m['status'], m['status'])}", style="List Bullet")

    doc.add_heading("Выявленные отклонения", level=2)
    findings = _verified(report)
    if not findings:
        doc.add_paragraph("Подтверждённых отклонений не выявлено.")
    for f in findings:
        doc.add_heading(f"{f['finding_id']}. {f['title']}", level=3)
        p = doc.add_paragraph(); p.add_run(f"{TYPE_RU.get(f['type'], f['type'])} ({f['severity']})").bold = True
        for e in f["evidence"]:
            q = doc.add_paragraph(e["quote"]); q.runs[0].italic = True
            doc.add_paragraph(f"— {e['doc_name']}, п. {e['clause']}")
        if f.get("recommendation"):
            p = doc.add_paragraph(); p.add_run("Рекомендация: ").bold = True; p.add_run(f["recommendation"])

    doc.save(path)
    return path
