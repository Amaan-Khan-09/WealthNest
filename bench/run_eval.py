"""Run the three arms on a fixture split and write per-case outputs + summary.

    python -m bench.run_eval --split dev
    python -m bench.run_eval --split holdout --out results

Arms (same inputs for each):
  1 baseline   straightforward parser, no checks
  2 validated  the same parser + validation / review routing
  3 full       robust extraction + recovery + validation / review routing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from statement_guard.pipeline import process

from .metrics import by_group, score_doc, summarize

ROOT = Path(__file__).resolve().parent.parent
ARMS = [("naive", "0. Naive first draft (disclosed)"), ("baseline", "1. Baseline parser"),
        ("validated", "2. Baseline + validation"), ("full", "3. Full pipeline (locked)"),
        ("full_fixed", "3b. Full pipeline + post-lock fixes")]


def load(split: str) -> list[tuple[Path, dict]]:
    d = ROOT / "fixtures" / split
    return [(p, json.loads(p.with_suffix(".truth.json").read_text(encoding="utf-8")))
            for p in sorted(d.glob("*.pdf"))]


def run(split: str) -> dict:
    items = load(split)
    from .lock import verify
    out: dict = {"split": split, "arms": {}, "per_case": {}, "lock": verify()}
    for mode, label in ARMS:
        scores = []
        for pdf, truth in items:
            st = process(pdf.read_bytes(), mode=mode, name=pdf.name)
            sc = score_doc(truth, st)
            sc["name"] = pdf.stem
            scores.append(sc)
        out["arms"][mode] = {"label": label, "summary": summarize(scores),
                             "by_category": by_group(scores, "category"), "by_layout": by_group(scores, "layout")}
        out["per_case"][mode] = scores
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "holdout"], default="dev")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    res = run(a.split)
    outdir = ROOT / a.out
    outdir.mkdir(exist_ok=True)
    (outdir / f"eval_{a.split}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    for mode, arm in res["arms"].items():
        s = arm["summary"]
        print(f"{arm['label']:28s} docs={s['docs']} fin_exact={s['doc_exact_financial']['k']}/{s['docs']} "
              f"recall={s['recall']['k']}/{s['recall']['n']} false_acc={s['false_acceptance']['k']}/{s['false_acceptance']['n']} "
              f"false_alarm={s['false_alarm']['k']}/{s['false_alarm']['n']} review={s['review_rate']['rate']:.0%} "
              f"fields d/a/b/desc="
              f"{s['field_date']['rate']:.3f}/{s['field_amount']['rate']:.3f}/{s['field_balance']['rate']:.3f}/{s['field_description']['rate']:.3f}")


if __name__ == "__main__":
    sys.exit(main())
