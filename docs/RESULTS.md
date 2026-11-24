# Results

Every number below comes from `python -m bench.run_eval` → `python -m bench.report`
(full tables: [`results/RESULTS_TABLES.md`](../results/RESULTS_TABLES.md), per-document outputs:
`results/per_case_holdout.csv`, `results/eval_holdout.json`). All data is synthetic.

## What was measured

| Item | Value |
|---|---|
| Dev fixtures (used to build the parser) | 56 PDFs, layouts A–D, 2,478 transaction rows |
| **Held-out fixtures** | **100 PDFs, 3,931 rows**: four layouts never used in development (E–H) × 20, plus fresh seeds of two dev layouts (A, C) × 10 |
| Fixture categories (every layout gets each) | clean, watermark, blank repeated dates, very wide amounts, overdraft, OCR-damaged text layer, source missing a row, source with a duplicated row, source with a tampered amount, image-only scan |
| Ground truth | defined by the generator's own ledger (exact `Decimal`), independent of the parser |
| Lock | fixture ground-truth hashes and pipeline source hashes frozen in `bench/LOCK.json` before the holdout run |

**Definitions.** *Problem document* = the extraction is wrong on any date/amount/balance/opening/closing, **or** the
printed statement itself is defective (missing row, duplicate row, altered amount), **or** the file is an image-only scan.
*Detection recall* = problem documents routed to review ÷ problem documents. *False acceptance* = problem documents that
were imported anyway. *False alarm* = fine documents sent to review. Description text is scored separately because
arithmetic checks cannot see it.

## Three comparisons on the same 100 held-out PDFs

| | 1. Baseline parser | 2. Same parser + validation | 3. Full pipeline (locked) |
|---|---|---|---|
| Fully correct statements | 32/100 | 32/100 | **87/100** (95% CI 79–92) |
| Problem documents (by that arm's own output) | 77 | 77 | 28 |
| Routed to review (recall) | 0/77 | **77/77** | **28/28** (CI 88–100) |
| **Silently imported while wrong** | **77 per 100** | 0 | **0** (CI 0–12% of 28) |
| False alarms (fine docs sent to review) | none (no checks) | 12/23 (52%) | 16/72 (22%) |
| Review rate | 0% | 89% | **44%** |
| Straight-through **and** correct | 23/100 | 11/100 | **56/100** |
| Date / amount / balance exact match | 69% / 52% / 85% | same | **95% / 94% / 96%** |

Reading it:
- **Arm 2 isolates error detection.** The checks alone catch every one of the 77 problem documents, but because the
  baseline extraction is poor, 89 of 100 statements go to a human, which is unusable.
- **Arm 3 adds extraction and recovery.** More statements come out right (87 vs 32), so far fewer need review (44 vs 89)
  while nothing wrong slips through on the financial fields.
- **Row localisation.** When the full pipeline flagged a problem document that had row-level flags, a flagged row was within
  ±1 of the true culprit in 21/21 cases.

## Where it is weak (read this before quoting the headline)

1. **Layout H is a 20-document false-alarm block by design.** H prints neither opening nor closing balance, so the
   pipeline refuses to call anything "ready" (`unanchored`). 16 of 20 H statements were extracted correctly and still sent to
   review. That is the *entire* false-alarm count and drags precision to 64%. It is a deliberate strict policy,
   with a cost.
2. **The locked pipeline had two real bugs the holdout exposed** (see "Post-lock changes"). On layout F it was *worse* than the
   baseline (13/20 vs 14/20 correct) until the indicator-column bug was fixed.
3. **Recovery masked a bug.** 13 of the 17 documents the locked pipeline auto-corrected were layout F *direction* repairs
   compensating for the indicator-column bug. All 17 were still correct, but this is "evidence-backed recovery worked" *and*
   "the parser was wrong", not a free win. After the fix 7 documents are auto-corrected, all from genuine OCR damage, all correct.
4. **Dev vs holdout.** The full pipeline scored 53/56 (95%) on dev and 87/100 (87%) held-out: the optimism of tuning on dev is about 8 points.
5. **Wrong descriptions are invisible to arithmetic.** 13 of the 100 held-out statements imported with right numbers but a wrong
   description in the locked pipeline (the indicator word leaked into the narration); 0 after the fix. The validator-only benchmark
   confirms 0% detection of description errors and of dates that are wrong but still in order.
6. **Without a running balance, offsetting errors pass.** Two amount errors that cancel are caught 100% of the time when a
   running balance exists and **0%** when only opening/closing balances exist (layout G-type statements).
7. **Image-only scans (4/100) are not extracted at all.** They are routed to review as `UNSUPPORTED`. OCR was not built.
8. **Synthetic only.** Seven invented layouts are not a sample of real bank statements. Nothing here estimates real-world accuracy.

## Post-lock changes (disclosed)

The benchmark was locked, then run once on the holdout. The results exposed problems that were fixed afterwards, and
`bench/LOCK.json` records each one:

| Change | Why | Effect on arms |
|---|---|---|
| **Baseline replaced.** The first draft ("naive", kept as arm 0) assigned every word, including narration, to the nearest column: it scored 9/100. That was a weak strawman. Baseline v1 classifies money tokens first, and a follow-up fix (v1.1) stopped it reading a narration word such as "D" as a Dr/Cr marker (found on dev data) | A baseline that fails for a silly reason proves nothing | Arms 1 and 2 only. Arm 3 unchanged. **Baseline v1 was written after seeing the naive result on holdout**, so its holdout number is not blind |
| Indicator-column window widened (layout F) | Header centred, values left-aligned: window was 4 pt too tight | Arm 3b only (`full_fixed`) |
| Header-free column inference counts rows with blank dates | Blank-date rows made debit/credit look like amount/balance (layout G) | Arm 3b only |

Arm 3 (`full`) runs the locked behaviour (`fixes=False`). Arm 3b (`full_fixed`, the demo default) is 93/100 correct and 41% review.
**3b was tuned after seeing holdout failures, so treat it as optimistic**, not as an unbiased held-out number.

## Validator-only benchmark (errors injected into extracted records, no PDFs)

300 seeded ledgers per cell. Detection = routed to review.

| Error injected | With running balance | Opening/closing only |
|---|---|---|
| dropped row | 100% | 100% |
| duplicated row | 100% | 100% |
| debit/credit flipped | 100% | 100% |
| amount digit changed | 100% | 100% |
| adjacent digits transposed | 100% | 100% |
| two offsetting amount errors | 100% | **0%** |
| printed balance wrong | 100% | n/a |
| date out of order | 100% | 100% |
| date wrong but still in order | **0%** | **0%** |
| description wrong | **0%** | **0%** |

This table keeps "the checks cannot see it" separate from "the parser did not make that mistake".

## Failures worth showing

- **Caught:** sample `2_amount_mismatch_caught.pdf`: row 4's printed amount is off by 1,000.00 against the printed balances; the baseline
  imports it, the pipeline stops it, shows the row with a red box on the source page and the reason.
- **Limitation:** layout H, all clean: extracted perfectly, still held back for lack of an opening/closing anchor.
- **Limitation:** `G_blank_date_7003` (locked run): header-free layout plus blank dates → debit/credit mistaken for amount/balance →
  the whole document wrong; every check failed loudly and it went to review (fixed in 3b).

## Runtime

Median 36–37 ms per PDF for the full pipeline (p95 63–68 ms) on a laptop, single thread. Enough for synchronous use in an import flow; not a scaling claim.

## Reproduce

```
python -m bench.make_fixtures --check        # fixtures match the lock
python -m bench.run_eval --split holdout     # all arms, ~minutes
python -m bench.injection_eval
python -m bench.report && python -m bench.charts
```
