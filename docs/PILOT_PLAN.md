# How WealthNest could test the product impact (hypotheses, not results)

Nothing here is measured. It is the plan for turning the benchmark into evidence.

## Hypotheses

| # | Hypothesis | Mechanism |
|---|---|---|
| H1 | Fewer wrong statement imports reach family net worth | Reconciliation stops imports whose numbers disagree with themselves |
| H2 | Fewer support tickets / re-imports about "my balance is wrong" | Errors are caught at import time with a reason, not discovered weeks later |
| H3 | More users get from "import" to "first linked account" | A visible, fixable "needs attention" state replaces silent failure or a dead end |
| H4 | Review workload stays tolerable | Most statements pass straight through (the benchmark's review rate is 41–44% on a deliberately hard synthetic mix; real mix unknown) |

The benchmark does **not** say how large any of these effects are on real statements.

## Pilot design (assumes WealthNest chooses to run it; not something this repo can do)

1. **Shadow mode first.** Run `statement_guard` alongside the existing importer on statements users *already consented to upload*,
   without changing what the user sees. Log only: status, flag codes, repair kinds, and (where the existing importer's output is
   available) agreement per field. No new data leaves the production boundary, and no statements are stored for the experiment
   beyond the existing retention policy.
2. **Audit sample.** Humans check a random sample (stratified by layout/bank) of statements marked READY and a sample marked
   NEEDS_REVIEW against the source PDF. This gives the number the benchmark cannot: the real **silent-error rate** and the real **false-alarm rate**.
3. **Go/no-go thresholds, set before looking** (suggested; WealthNest should choose): silent errors among READY ≤ 0.5% of
   statements (upper CI bound reported); false alarms ≤ 20%; median latency ≤ 1 s.
4. **Then an A/B**: new users randomised to (a) current flow, (b) guarded flow with the review screen. Primary metric:
   share reaching a first account with verified balances. Secondary: tickets per 1,000 imports, import abandonment, review completion time.
5. **Coverage report.** Share of real statements that land in `UNSUPPORTED` (image-only etc.). This decides whether OCR is the next investment.

## Public-information integration assumptions

- Accounts connected through the Account Aggregator framework arrive as structured FI data (the public ReBIT deposit schema carries
  a summary with current balance and a transactions list with narration, value date and reference). Statement PDFs are the
  **fallback path** for what AA does not deliver. `export.to_aa_like()` emits an illustrative record in that shape so downstream
  de-duplication and net-worth code would not care where a row came from. Field names and the DEBIT/CREDIT enum are **our assumption**;
  verify against ReBIT v2.0.0, and against WealthNest's internal schema, which this project has not seen.
- Cheap fit: a synchronous function call (~40 ms median) behind the upload endpoint, returning `{status, statement, flags}`.
  The review screen is the part that needs product design; `app/streamlit_app.py` is a working sketch of it.
- Security note: the parser runs in-process on untrusted PDFs with size/page/word caps. In production it should run in a sandboxed worker
  with a timeout and memory limit; this prototype does not provide that isolation.
