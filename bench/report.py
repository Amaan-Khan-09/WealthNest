"""Generate results/RESULTS_TABLES.md, results/per_case_<split>.csv and results/summary.json directly from the
evaluation JSON files. Nothing in the tables is typed by hand.

    python -m bench.report
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .metrics import wilson

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
ARM_ORDER = ["naive", "baseline", "validated", "full", "full_fixed"]


def pct(k: int, n: int, ci: bool = True) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    base = f"{k}/{n} ({100 * k / n:.0f}%)"
    return base + (f" [{100 * lo:.0f}–{100 * hi:.0f}]" if ci else "")


def arm_stats(cases: list[dict]) -> dict:
    n = len(cases)
    wrong_or_defect = [c for c in cases if c["positive"]]
    ok = [c for c in cases if not c["positive"]]
    return {
        "n": n,
        "exact": sum(not c["fin_error"] for c in cases),
        "positives": len(wrong_or_defect),
        "caught": sum(c["flagged"] for c in wrong_or_defect),
        "silent_wrong": sum(c["accepted"] for c in wrong_or_defect),
        "good": len(ok),
        "false_alarms": sum(c["flagged"] for c in ok),
        "flagged": sum(c["flagged"] for c in cases),
        "straight_through_correct": sum(c["accepted"] and not c["positive"] for c in cases),
        "desc_only_wrong_imported": sum(c["accepted"] and c["any_error"] and not c["positive"] for c in cases),
        "autofixed": sum(c["status"] == "READY_AUTOFIXED" for c in cases),
        "autofixed_correct": sum(c["status"] == "READY_AUTOFIXED" and not c["positive"] for c in cases),
        "loc": [c["loc_hit"] for c in cases if c["loc_hit"] is not None],
    }


def table_main(ev: dict, title: str) -> str:
    out = [f"### {title}\n",
           f"Documents: {ev['arms']['baseline']['summary']['docs']}; ground-truth rows: "
           f"{ev['arms']['baseline']['summary']['truth_rows']}. Brackets are Wilson 95% intervals.\n",
           "| Measure | " + " | ".join(ev["arms"][a]["label"] for a in ARM_ORDER) + " |",
           "|---|" + "---|" * len(ARM_ORDER)]
    S = {a: ev["arms"][a]["summary"] for a in ARM_ORDER}
    A = {a: arm_stats(ev["per_case"][a]) for a in ARM_ORDER}

    def row(name, fn):
        out.append(f"| {name} | " + " | ".join(fn(a) for a in ARM_ORDER) + " |")

    row("Documents fully correct (dates, amounts, balances, opening/closing)", lambda a: pct(A[a]["exact"], A[a]["n"]))
    for f, nm in (("date", "date"), ("amount", "debit/credit amount"), ("balance", "running balance"),
                  ("description", "description (whitespace-insensitive)")):
        row(f"Field exact match: {nm}", lambda a, f=f: pct(S[a][f"field_{f}"]["k"], S[a][f"field_{f}"]["n"], ci=False))
    row("Rows missed / extra", lambda a: f"{S[a]['rows_missed']['k']} / {S[a]['rows_extra']['k']} (of {S[a]['rows_missed']['n']})")
    row("Problem documents (wrong extraction or defective source or unreadable)", lambda a: f"{A[a]['positives']}")
    row("…of which flagged for review (detection recall)", lambda a: pct(A[a]["caught"], A[a]["positives"]))
    row("…of which imported anyway (false acceptance)", lambda a: pct(A[a]["silent_wrong"], A[a]["positives"]))
    row("Detection precision (flagged docs that were really problems)",
        lambda a: pct(A[a]["caught"], A[a]["flagged"]) if A[a]["flagged"] else "n/a (no checks)")
    row("False alarms (fine documents sent to review)", lambda a: pct(A[a]["false_alarms"], A[a]["good"]))
    row("Review rate (all documents)", lambda a: pct(A[a]["flagged"], A[a]["n"], ci=False))
    row("Silently wrong imports (per 100 documents)", lambda a: f"{100 * A[a]['silent_wrong'] / A[a]['n']:.0f}")
    row("Imported with right numbers but a wrong description (arithmetic cannot see this)",
        lambda a: f"{A[a]['desc_only_wrong_imported']}/{A[a]['n']}")
    row("Straight-through and correct", lambda a: pct(A[a]["straight_through_correct"], A[a]["n"], ci=False))
    row("Auto-corrected docs: correct", lambda a: pct(A[a]["autofixed_correct"], A[a]["autofixed"]) if A[a]["autofixed"] else "–")
    row("Row localisation (a flagged row within ±1 of the true culprit)",
        lambda a: pct(sum(A[a]["loc"]), len(A[a]["loc"])) if A[a]["loc"] else "–")
    row("Median runtime per PDF (ms)", lambda a: f"{S[a]['runtime_ms_median']:.0f}")
    return "\n".join(out) + "\n"


def table_group(ev: dict, key: str, title: str, arms=("baseline", "full", "full_fixed")) -> str:
    groups = list(ev["arms"]["full"][f"by_{key}"].keys())
    out = [f"### {title}\n", "Each cell: documents fully correct / documents; then flagged for review.\n",
           "| " + key.capitalize() + " | Docs | " + " | ".join(
               f"{ev['arms'][a]['label']}: correct · flagged" for a in arms) + " |",
           "|---|---|" + "---|" * len(arms)]
    for g in groups:
        n = ev["arms"]["full"][f"by_{key}"][g]["n"]
        cells = []
        for a in arms:
            d = ev["arms"][a][f"by_{key}"][g]
            cells.append(f"{d['fin_exact']}/{d['n']} · {d['flagged']}")
        out.append(f"| {g} | {n} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def table_injection(inj: dict) -> str:
    out = ["### Validator-only benchmark: errors injected directly into extracted records\n",
           f"{inj['n_per_cell']} seeded ledgers per cell. Detection = statement routed to review.\n",
           "| Error injected | With running balance | Opening/closing balance only |", "|---|---|---|"]
    names = []
    for v in inj["cells"].values():
        if v["error"] not in names:
            names.append(v["error"])
    for nm in names:
        a = inj["cells"].get(f"{nm} | running balance")
        b = inj["cells"].get(f"{nm} | opening/closing only")
        fa = pct(a["k"], a["n"]) if a else "–"
        fb = pct(b["k"], b["n"]) if b else "–"
        out.append(f"| {nm} | {fa} | {fb} |")
    return "\n".join(out) + "\n"


def write_csv(ev: dict) -> None:
    sp = ev["split"]
    with open(RES / f"per_case_{sp}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case", "layout", "category", "truth_rows", "arm", "status", "financial_error", "expected_review",
                    "missed", "extra", "repairs", "flag_codes", "runtime_ms"])
        for arm in ARM_ORDER:
            for c in ev["per_case"][arm]:
                w.writerow([c["name"], c["layout"], c["category"], c["n_truth"], arm, c["status"], int(c["fin_error"]),
                            int(c["expected_review"]), c["missed"], c["extra"], c["n_repairs"],
                            ";".join(c["flag_codes"]), c["runtime_ms"]])


def main() -> None:
    parts = ["# Results tables (generated by `python -m bench.report`; do not edit by hand)\n"]
    summary = {}
    for sp, title in (("holdout", "Held-out evaluation (locked before the run; 4 unseen layouts + fresh seeds of 2 dev layouts)"),
                      ("dev", "Development set (used to build the parser: optimistic, shown for transparency)")):
        p = RES / f"eval_{sp}.json"
        if not p.exists():
            continue
        ev = json.loads(p.read_text(encoding="utf-8"))
        parts.append(table_main(ev, title))
        parts.append(table_group(ev, "category", f"{sp}: by fixture category"))
        parts.append(table_group(ev, "layout", f"{sp}: by layout"))
        write_csv(ev)
        summary[sp] = {a: arm_stats(ev["per_case"][a]) | {"label": ev["arms"][a]["label"]} for a in ARM_ORDER}
        for a in summary[sp]:
            summary[sp][a]["loc"] = [int(x) for x in summary[sp][a]["loc"]]
        parts.append(f"_Lock status when run: {ev['lock']}_\n")
    inj = RES / "injection.json"
    if inj.exists():
        parts.append(table_injection(json.loads(inj.read_text())))
    (RES / "RESULTS_TABLES.md").write_text("\n".join(parts), encoding="utf-8")
    (RES / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("wrote results/RESULTS_TABLES.md, summary.json, per_case_*.csv")


if __name__ == "__main__":
    main()
