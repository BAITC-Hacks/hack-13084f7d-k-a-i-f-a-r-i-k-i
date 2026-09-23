"""Оркестратор: before/after → Report (contracts.md).   Владелец: роль 1.

CLI:  python -m pipeline.run data/test_set/before data/test_set/after -o output/report.json
"""
import argparse, json, datetime
from pathlib import Path
from .parse import parse_folder
from .extract import extract
from .match_units import match_units
from .match_functions import match_functions
from .duplicates import find_duplicates
from .conflicts import find_conflicts
from .verifier import verify
from .report import build_summary
from .schemas import evidence_from_chunk


def loss_findings(function_map, functions, chunks):
    fby = {f["func_id"]: f for f in functions}
    cby = {c["chunk_id"]: c for c in chunks}
    out = []
    for m in function_map:
        if m["status"] != "lost":
            continue
        f = fby[m["func_id"]]
        ch = cby[f["source"]["chunk_id"]]
        out.append({"finding_id": "", "type": "loss", "severity": "high",
                    "title": f"Возможная потеря функции: {f['text'].rstrip('.')}",
                    "description": f"Функция подразделения {f['unit_id']} не найдена в документах «после». {m['rationale']}",
                    "evidence": [evidence_from_chunk(ch, f["source"]["quote"])],
                    "recommendation": "Закрепить функцию за одним из подразделений в новой редакции положений."})
    return out


def run(before_dir, after_dir, use_llm=False, log=print) -> dict:
    log("Шаг 1/7: парсинг документов")
    chunks = parse_folder(before_dir, "before") + parse_folder(after_dir, "after")
    log(f"  чанков: {len(chunks)}")
    log("Шаг 2/7: извлечение подразделений и функций")
    units, functions = extract(chunks, use_llm=use_llm)
    log(f"  подразделений: {len(units)}, функций: {len(functions)}")
    log("Шаг 3/7: сопоставление подразделений")
    unit_map = match_units(units, functions, chunks, log=log)
    log("Шаг 4/7: сопоставление функций")
    function_map = match_functions(functions, unit_map, log=log)
    log("Шаг 5/7: дубли и конфликты интересов")
    findings = loss_findings(function_map, functions, chunks)
    findings += find_duplicates(functions, units, log=log)
    findings += find_conflicts(functions, units, log=log)
    log("Шаг 6/7: верификация цитат")
    ok, bad = verify(findings, chunks, log=log)
    for i, f in enumerate(ok, 1):
        f["finding_id"] = f"F{i}"
    report = {"meta": {"created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                       "before_docs": sorted({c["doc_name"] for c in chunks if c["side"] == "before"}),
                       "after_docs": sorted({c["doc_name"] for c in chunks if c["side"] == "after"}),
                       "models": {}},
              "units": units, "functions": functions, "unit_map": unit_map, "function_map": function_map,
              "findings": ok, "rejected_findings": bad, "summary": "", "log": []}
    log("Шаг 7/7: заключение")
    report["summary"] = build_summary(report)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("before"); ap.add_argument("after")
    ap.add_argument("-o", "--out", default="output/report.json")
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    logs = []
    rep = run(a.before, a.after, use_llm=a.llm, log=lambda s: (print(s), logs.append(s)))
    rep["log"] = logs
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {a.out}")
