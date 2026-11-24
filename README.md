# Statement Guard

WealthNest National Case Study Challenge 2026: **Product Engineering & AI → Sub-track C (AI), problem 1: statement parsing.**
A bank-statement PDF extractor that **checks itself**: it reconciles every number against the statement's own arithmetic, stops what does not
add up, and shows a reviewer the suspect row, the evidence and the reason.

> Synthetic data only. No real statement, account or WealthNest data is used anywhere. Nothing here claims how the live WealthNest importer behaves.
> Status of the submission: see [Open items](#open-items).

## Quick start

Tested on Python 3.14 / Windows 11.

```bash
pip install -r requirements.txt
python -m pytest -q                                   # 63 tests
python -m statement_guard.cli fixtures/samples/2_amount_mismatch_caught.pdf
streamlit run app/streamlit_app.py                    # demo + review flow (http://localhost:8501)
```

| Task | Command |
|---|---|
| Extract + verify one PDF | `python -m statement_guard.cli file.pdf [--mode full_fixed] [--json out.json] [--csv out.csv]` |
| Build fixtures (seeded) | `python -m bench.make_fixtures` (writes `fixtures/dev`, `fixtures/holdout`); `--check` verifies the lock |
| Run the benchmark | `python -m bench.run_eval --split holdout` (and `--split dev`) |
| Validator-only benchmark | `python -m bench.injection_eval` |
| Tables + per-case CSV | `python -m bench.report` → `results/RESULTS_TABLES.md`, `results/per_case_*.csv` |
| Charts + diagram | `python -m bench.charts` → `docs/img/` |
| Rebuild the deck PDF | `python submission/deck/make_assets.py && python submission/deck/build_deck.py` |

Pipeline modes: `naive` (disclosed first draft), `baseline`, `validated`, `full` (code frozen at the benchmark lock), `full_fixed` (default; includes two post-lock fixes).

## Result in one paragraph (held-out, 100 synthetic PDFs, 3,931 rows)

The straightforward baseline imported 77 statements with wrong numbers. The full pipeline had no wrong imports among its 28 problem
documents (28/28 flagged, 95% CI 88–100%), read 87/100 statements fully correctly (baseline 32/100) and sent 44% to review (checks bolted onto the
baseline: 89%). Where it is weak: statements without opening/closing balances are always held back (16 false alarms), arithmetic cannot see wrong descriptions
or in-order date errors, image-only scans are unsupported, and the benchmark is synthetic. Read [`docs/RESULTS.md`](docs/RESULTS.md) for the
full tables, the post-lock changes and the caveats before quoting any number.

## Repository map

```
statement_guard/   money.py  models.py  extract.py  baseline.py  validate.py  recover.py  review.py  pipeline.py  export.py  cli.py
bench/             generator.py  make_fixtures.py  metrics.py  run_eval.py  injection_eval.py  lock.py  report.py  charts.py  LOCK.json
app/               streamlit_app.py            demo + review UI
tests/             63 tests: money, validator (record-level error injection), PDF pipeline, robustness/fuzz, exports and CLI, reviewer fix, app smoke
fixtures/          dev/ holdout/ (generated)  samples/ (5 demo PDFs)
results/           eval_*.json  RESULTS_TABLES.md  per_case_*.csv  injection.json  summary.json
docs/              SCOPE_DECISION  ARCHITECTURE  RESULTS  REVIEW_NOTES  PILOT_PLAN  audit/ (checklist + evidence template)  img/
submission/        deck/slides.html (editable)  TeamName_Tech.pdf  unstop_form_draft.md  DEMO_SCRIPT.md  QA_PREP.md
```

## How the benchmark stays honest

- **Independent ground truth:** the generator builds a `Decimal` ledger first, then renders it with reportlab; the parser uses PyMuPDF.
- **Dev vs. held-out:** layouts E–H and the holdout seeds were never used to develop the parser.
- **Lock:** `bench/LOCK.json` stores fixture-truth and source hashes from before the holdout run, and lists every change made afterwards (including the replaced baseline).
- **Separate tests:** PDF-level results and record-level error injection are reported separately.
- **Denominators and intervals** everywhere; the tables are generated, not typed.

## Open items

Things only the team can supply. The package is **not ready to upload** until these are done:

1. **Live-app audit evidence** (30% of the score): **not performed yet, 0 of 3 observations verified.** The assistant cannot operate a mobile app. The official link
   (`wealthnest.sng.link/D7wl6/n0lh6` → Play `com.wealthnest.app` / App Store `id6757753223`, Tatvartha WealthNest AI Pvt Ltd) is verified. Follow
   [`docs/audit/AUDIT_HANDOFF.md`](docs/audit/AUDIT_HANDOFF.md) (exact run sheet and the synthetic files in `fixtures/samples/` and `fixtures/audit/`),
   then fill [`docs/audit/AUDIT_EVIDENCE.md`](docs/audit/AUDIT_EVIDENCE.md), slide 2 and the form's 100-word observations.
2. **Team name and any second member** (slide 1); rename `TeamName_Tech.pdf` accordingly.
3. **Your individual contribution**: confirm it, then add it to the Q&A notes.
4. Rebuild the deck (`python submission/deck/build_deck.py`), re-check the PDF, upload on Unstop yourself.

Done: public repo [github.com/Amaan-Khan-09/WealthNest](https://github.com/Amaan-Khan-09/WealthNest); GitHub Actions passed on `a36d0ca`.

## Known limitations

Synthetic layouts only; text-layer PDFs only (no OCR); single-account bank statements; descriptions and in-order dates are not verified by arithmetic; in-process parsing of
untrusted PDFs is not sandboxed. See [`docs/RESULTS.md`](docs/RESULTS.md) and [`docs/SCOPE_DECISION.md`](docs/SCOPE_DECISION.md).
