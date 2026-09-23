"""Сравнение report.json с эталоном ground_truth.json.   Владелец: роль 2.

python eval.py output/report.json data/test_set/ground_truth.json
Совпадение: тот же тип вывода + все пункты эталона (doc + clause) присутствуют в evidence.
"""
import json, sys


def refs(ev):
    return {(e["doc_name"] if "doc_name" in e else e["doc"], e["clause"]) for e in ev}


def main(report_path, gt_path):
    rep = json.load(open(report_path, encoding="utf-8"))
    gt = json.load(open(gt_path, encoding="utf-8"))
    expected = [("loss", x["id"], [x["function"]]) for x in gt["function_losses"]]
    expected += [("duplicate", x["id"], [x["a"], x["b"]]) for x in gt["duplications"]]
    expected += [("conflict", x["id"], [x["a"], x["b"]]) for x in gt["conflicts_of_interest"]]
    found = [(f["type"], refs(f["evidence"])) for f in rep["findings"]]
    hit_findings = set()
    print(f"{'ID':4} {'тип':10} результат")
    tp = 0
    for typ, gid, gev in expected:
        need = refs(gev)
        idx = next((i for i, (t, r) in enumerate(found) if t == typ and need <= r), None)
        ok = idx is not None
        tp += ok
        if ok:
            hit_findings.add(idx)
        print(f"{gid:4} {typ:10} {'✔ найдено' if ok else '✘ пропущено'}  {sorted(need)}")
    # бонус / допустимые — не считаются ложными
    allowed = [refs([x["a"], x["b"]]) for x in gt.get("conflicts_optional", [])]
    allowed += [refs([x["function"]]) for x in gt.get("partial_or_borderline", [])]
    fp = [f for i, f in enumerate(found) if i not in hit_findings and not any(a <= f[1] for a in allowed)]
    print(f"\nНайдено {tp} из {len(expected)} эталонных случаев; ложных срабатываний: {len(fp)}")
    for t, r in fp:
        print(f"  ложное: {t} {sorted(r)}")


if __name__ == "__main__":
    main(*(sys.argv[1:3] if len(sys.argv) >= 3 else ["output/report.json", "data/test_set/ground_truth.json"]))
