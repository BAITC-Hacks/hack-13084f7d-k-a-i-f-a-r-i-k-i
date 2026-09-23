"""Шаг 7. Итоговое заключение и экспорт.   Владелец: роль 4 (+ роль 1 для LLM-заключения).

TODO: build_summary_llm() — сильная модель пишет заключение ТОЛЬКО по verified findings
(передавать в промпт findings, а не документы — так модель не выдумает новых фактов).
TODO: export_docx().
"""
TYPE_RU = {"loss": "Потеря функции", "duplicate": "Дублирование", "conflict": "Конфликт интересов"}
STATUS_RU = {"kept": "сохранено", "renamed": "переименовано", "merged": "объединено", "split": "разделено",
             "abolished": "упразднено", "created": "создано", "modified": "изменено"}


def build_summary(report: dict) -> str:
    lines = ["## Итоговое заключение", "",
             "_Выводы носят рекомендательный характер и требуют проверки ответственным сотрудником._", ""]
    lines.append("### Изменения подразделений")
    for m in report["unit_map"]:
        ids = ", ".join(m["before_ids"]) or "—"
        ids2 = ", ".join(m["after_ids"]) or "—"
        lines.append(f"- {ids} → {ids2}: **{STATUS_RU.get(m['status'], m['status'])}**")
    lines += ["", "### Выявленные отклонения"]
    if not report["findings"]:
        lines.append("Подтверждённых отклонений не выявлено.")
    for f in report["findings"]:
        src = "; ".join(f"{e['doc_name']} п.{e['clause']}" for e in f["evidence"])
        lines.append(f"- **{TYPE_RU.get(f['type'], f['type'])}** ({f['severity']}): {f['title']}. Источник: {src}")
    return "\n".join(lines)


def to_markdown(report: dict) -> str:
    md = [report["summary"], "", "### Подтверждающие цитаты"]
    for f in report["findings"]:
        md.append(f"**{f['finding_id']}. {f['title']}**")
        for e in f["evidence"]:
            md.append(f"> {e['quote']}  \n> — {e['doc_name']}, п. {e['clause']}")
        if f.get("recommendation"):
            md.append(f"Рекомендация: {f['recommendation']}")
        md.append("")
    return "\n".join(md)
