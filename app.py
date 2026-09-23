"""UI.   Владелец: роль 4.   Запуск: streamlit run app.py"""
import json, os, tempfile
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="OrgScan — анализ оргструктуры", page_icon="🏢", layout="wide")
st.title("🏢 OrgScan — анализ организационной структуры")
st.caption("Выводы носят рекомендательный характер и требуют проверки ответственным сотрудником. "
           "Каждый вывод подтверждён цитатой из документа.")

TYPE_RU = {"loss": "🔴 Потеря функции", "duplicate": "🟠 Дублирование", "conflict": "🟣 Конфликт интересов"}
STATUS_RU = {"kept": "🟢 сохранено", "renamed": "🔵 переименовано", "merged": "🟡 объединено", "split": "🟡 разделено",
             "abolished": "🔴 упразднено", "created": "🟢 создано", "modified": "⚪ изменено"}

with st.sidebar:
    st.header("Документы")
    src = st.radio("Источник", ["Тестовый комплект", "Загрузить свои", "Демо-отчёт (mock)"],
                   index=2 if os.getenv("USE_MOCK") == "1" else 0)
    up_before = up_after = None
    if src == "Загрузить свои":
        up_before = st.file_uploader("Комплект «ДО»", type=["docx", "pdf", "xlsx"], accept_multiple_files=True)
        up_after = st.file_uploader("Комплект «ПОСЛЕ»", type=["docx", "pdf", "xlsx"], accept_multiple_files=True)
    use_llm = st.toggle("Использовать LLM", value=False)
    go = st.button("Анализировать", type="primary", width="stretch")


def save_uploads(files, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        (folder / f.name).write_bytes(f.getbuffer())
    return folder


if go:
    if src == "Демо-отчёт (mock)":
        st.session_state.report = json.loads(Path("data/mock_report.json").read_text(encoding="utf-8"))
    else:
        from pipeline.run import run
        if src == "Тестовый комплект":
            b, a = "data/test_set/before", "data/test_set/after"
        else:
            if not up_before or not up_after:
                st.error("Загрузите оба комплекта"); st.stop()
            tmp = Path(tempfile.mkdtemp())
            b, a = save_uploads(up_before, tmp / "before"), save_uploads(up_after, tmp / "after")
        logs = []
        with st.status("Агент анализирует документы…", expanded=True) as s:
            def log(msg):
                logs.append(msg); st.write(msg)
            rep = run(b, a, use_llm=use_llm, log=log)
            rep["log"] = logs
            s.update(label="Готово", state="complete")
        st.session_state.report = rep

rep = st.session_state.get("report")
if not rep:
    st.info("Выберите источник документов слева и нажмите «Анализировать».")
    st.stop()

f = rep["findings"]
c = st.columns(4)
c[0].metric("Изменения подразделений", sum(m["status"] != "kept" for m in rep["unit_map"]))
c[1].metric("Потери функций", sum(x["type"] == "loss" for x in f))
c[2].metric("Дублирования", sum(x["type"] == "duplicate" for x in f))
c[3].metric("Конфликты интересов", sum(x["type"] == "conflict" for x in f))

tabs = st.tabs(["Заключение", "Подразделения", "Отклонения", "Таблица функций", "Отклонено верификатором", "Лог агента"])

with tabs[0]:
    st.markdown(rep["summary"])
    from pipeline.report import to_markdown
    st.download_button("⬇ Скачать заключение (Markdown)", to_markdown(rep), "zaklyuchenie.md")
    st.download_button("⬇ Скачать отчёт (JSON)", json.dumps(rep, ensure_ascii=False, indent=2), "report.json")

with tabs[1]:
    names = {u["unit_id"]: f"{u['code']} — {u['name']}" for u in rep["units"]}
    rows = [{"До": "\n".join(names.get(i, i) for i in m["before_ids"]) or "—",
             "После": "\n".join(names.get(i, i) for i in m["after_ids"]) or "—",
             "Статус": STATUS_RU.get(m["status"], m["status"]), "Обоснование": m["rationale"],
             "Источник": "; ".join(f"{e['doc_name']} п.{e['clause']}" for e in m["evidence"])} for m in rep["unit_map"]]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

with tabs[2]:
    kinds = st.multiselect("Тип", list(TYPE_RU), default=list(TYPE_RU), format_func=TYPE_RU.get)
    for x in [x for x in f if x["type"] in kinds]:
        with st.expander(f"{TYPE_RU[x['type']]} · {x['severity']} · {x['title']}"):
            st.write(x["description"])
            for e in x["evidence"]:
                st.markdown(f"> «{e['quote']}»  \n📄 **{e['doc_name']}**, п. {e['clause']}"
                            + (f", стр. {e['page']}" if e.get("page") else ""))
            if x.get("recommendation"):
                st.success(f"Рекомендация: {x['recommendation']}")

with tabs[3]:
    fby = {x["func_id"]: x for x in rep["functions"]}
    rows = [{"Функция «до»": fby[m["func_id"]]["text"], "Подразделение": m["func_id"].rsplit(":", 1)[0],
             "Статус": m["status"], "Где теперь": ", ".join(m["matched_func_ids"]), "Оценка": m["score"],
             "Обоснование": m["rationale"]} for m in rep["function_map"] if m["func_id"] in fby]
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)

with tabs[4]:
    st.caption("Кандидаты, которые агент сгенерировал, но не смог подтвердить цитатой из документов.")
    for x in rep.get("rejected_findings", []):
        st.warning(f"{x['title']} — {x.get('verify_note', '')}")
    if not rep.get("rejected_findings"):
        st.write("Нет отклонённых выводов.")

with tabs[5]:
    st.code("\n".join(rep.get("log", [])))
