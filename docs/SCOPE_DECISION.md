# Scope decision

**Decision:** Indian bank-statement PDFs (text layer), extracting opening balance, closing balance and
transaction rows (date, description, debit, credit, running balance), then reconciling them.

**Status of the evidence behind this choice: PROVISIONAL.** No real WealthNest app observations have been
supplied yet (see `docs/audit/AUDIT_EVIDENCE.md`). The default scope below is justified from the case brief
and public facts only. If the live-app audit shows a stronger failure on another statement type (mutual-fund
CAS, demat holdings), revisit this file *before* building more.

## Why bank statements (default)

| Reason | Basis |
|---|---|
| The brief names statement parsing first: "bank, mutual fund, demat … dozens of layouts … catches its own extraction errors" | Case brief, Sub-track C, problem 1 |
| Bank statements carry **redundancy we can verify against**: opening + credits − debits = closing, and a running balance on every row | Document structure (not a WealthNest claim) |
| That redundancy lets the system *measure its own errors* without human labels, which is the "catches its own extraction errors" half of the brief | Design argument |
| Holdings statements (MF/demat) have far weaker internal checks (a unit count × NAV ≠ anything printed on every row), so a self-check benchmark would be much shakier | Design argument |
| A family imports many accounts; one silently wrong import corrupts a *family-level* net worth, so the cost of a false "OK" is amplified | Brief: "family-level net worth", Smart Insights |

## What is in scope

- Text-layer PDFs, A4, one or several pages, one account per file.
- Layout variation: split debit/credit columns, single amount with Dr/Cr suffix, Dr/Cr indicator column, no
  running balance, several summary styles (inline, summary box, opening/closing rows, none), wrapped narrations,
  repeated page headers/footers, carry-forward rows, blank repeated dates, watermarks, Indian digit grouping,
  overdraft balances, and OCR-damaged text layers.
- Detection of source defects (a row missing or duplicated in the printed statement, an amount inconsistent with
  the printed balances).

## Explicitly out of scope (and routed to review, not guessed)

- **Image-only scans.** No OCR is implemented (no OCR engine was available and reproducibility mattered more). They
  return `UNSUPPORTED` with a reason. This is a deliberate fail-safe.
- Password-protected PDFs, files over 15 MB or 40 pages.
- Multi-account PDFs, foreign-currency statements, mutual-fund and demat statements.
- Real bank layouts: the benchmark uses invented banks and layouts. Generalisation to real statements is
  **unmeasured**.

## Claims we do not make

- Nothing about how the live WealthNest importer behaves or performs. The "baseline" is our own reproduction of a
  straightforward parser.
- No claim that benchmark accuracy transfers to production statements.
- Product-impact numbers are hypotheses (see `docs/PILOT_PLAN.md`).
