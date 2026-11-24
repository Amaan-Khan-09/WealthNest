# Live-app audit: handoff (exactly what only you can do)

**Status (2026-11-25 session): NOT PERFORMED.** The assistant had no browser, device or computer-use tool and could not locate a verified
official app link (the case brief still contains the unfilled placeholder `{{App link}}`). Nothing about the app was observed, so
`AUDIT_EVIDENCE.md` is empty on purpose. Do not let any slide claim otherwise.

## Before you start
1. **Get the official link** from the Unstop challenge page ("Case Brief" attachment / listing) or ask the organisers:
   info@wealthnest.ai (brief) or careers@wealthnest.ai (listing contact). Check the publisher name against `wealthnest.ai`: a different app called "Wealthnest" exists on the App Store.
2. **Ask the organisers the open question the brief itself flags:** is there a demo mode that works without linking real accounts?
3. Use **only the synthetic files below**. Never link a real account or upload a real statement. Blur anything personal in every screenshot.

## Files to use (all synthetic, known answers)
| File | What it is | Known result in our prototype |
|---|---|---|
| `fixtures/samples/1_clean_statement.pdf` | 45-row clean statement | READY |
| `fixtures/samples/2_amount_mismatch_caught.pdf` | printed amount off by 1,000.00 at row 4 | NEEDS_REVIEW (row 4) |
| `fixtures/audit/short_statement_synthetic.pdf` | 3-row statement (ordinary edge case) | READY (3 rows, opening 10,000.00, closing 12,500.00) |
| `fixtures/samples/5_scanned_image_only.pdf` | image-only scan | UNSUPPORTED |

Regenerate the short file with `python -m bench.make_audit_fixtures`.

## 30-minute run sheet (record the exact words on screen)
**A. Find statement import (≈5 min).** Where does it sit: onboarding, "add account", a menu? How many taps from the home screen? What does the app say about supported documents, banks, size, password-protected files?
**B. Clean file (≈8 min).** Import file 1. Record: accepted or rejected; progress feedback; the exact status/message; what you can inspect afterwards (dates, transactions, balances, opening/closing); did anything change in net worth.
**C. Edge case (≈8 min).** Import the short statement, then the image-only scan (or the mismatch file if the app takes it). Record the exact user-facing message and the recovery options (retry, edit, contact support, manual entry).
**D. Review step (≈6 min).** If extracted data is shown: can you see each row? is anything flagged? can you correct a value or retry? what happens on re-importing the same file?
**E. Wrap-up (≈3 min).** What confused you, what felt slow, what would make you come back.

If a step is gated (OTP, account linking, a required document type), write down the **exact gate and screen** and stop there. Do not describe what happens after it.

## Record each observation like this
| Field | Example of what to write |
|---|---|
| 1. Path | Home → Add accounts → Import statement |
| 2. Action + fixture | Selected `2_amount_mismatch_caught.pdf` |
| 3. What appeared (verbatim) | "..." |
| 4. Why it matters for someone importing a family member's statement | one sentence |
| 5. Screenshot | `docs/audit/img/obs1.png` (blurred) |
| Label | `[OBSERVED]` only for things you saw; `[HYPOTHESIS]` for inference about internals |

## After you have three observations
1. Fill `AUDIT_EVIDENCE.md`.
2. Replace the three PENDING cards on **slide 2** in `submission/deck/slides.html` and tell me which observation is strongest: I will choose the demo case to match (the deck already shows sample 2 as a *proposed improvement*; a real observation can sharpen or replace that framing).
3. Fill the 100-word block in `submission/unstop_form_draft.md` (≤ 100 words total).
4. Rebuild: `python submission/deck/build_deck.py`.

## Mapping from a possible observation to the strongest demo
| If the app… | Then show… |
|---|---|
| accepts the mismatched file with no warning | sample 2: "same file, stopped with the exact row" (proposed improvement) |
| rejects any PDF with a generic error | sample 2 + review flow: "say *which row* and let the user fix it" |
| shows extracted rows but no flags | sample 2's flagged review card |
| rejects the image-only file with a clear message | sample 5: agree, and show our `UNSUPPORTED` handling |
| never shows an extraction result | keep the deck's framing: synthetic proposal only |
