# Live-app audit: handoff (exactly what only you can do)

**Status (2026-11-25, second attempt): STILL NOT PERFORMED. 0 of 3 in-app observations verified.**
The assistant has no browser, device or computer-use tool, so it cannot open or operate the mobile app. What it *could* do, and did:
resolve the official link, confirm the publisher, and read the **public store listings** (labelled `[STORE LISTING]` below: marketing text, **not** in-app observations).

## 1. Official link (from the Unstop listing), verified
`https://wealthnest.sng.link/D7wl6/n0lh6?_smtype=3` is a smart link. Plain HTTP requests, no login, no app interaction:

| Device | Redirects to | Result |
|---|---|---|
| Android | `https://play.google.com/store/apps/details?id=com.wealthnest.app` | Play listing **"WealthNest: Grow Family Wealth"**, publisher **WealthNest AI** |
| iPhone | `https://apps.apple.com/app/id6757753223` | App Store listing **"WealthNest: Grow Family Wealth App"**, developer **Tatvartha WealthNest AI Pvt Ltd**, "SEBI-Registered Investment Adviser, INA000022464", contact info@wealthnest.ai |
| Desktop | the Play listing above | |

The publisher and the SEBI number match the entity in the case brief, so this is the official app. (A different app called "Wealthnest" by another company exists; ignore it.)
**Install it from the link on your phone.** Free, "no card needed" per the listing. Sign in with your own account; do not link a real bank account.

## 2. `[STORE LISTING]` what the public listing says about statement import (not verified in the app)
Quoted from the App Store page (version history and description). Treat as claims to *check*, not as findings.
- "Link your accounts securely, **or import your CAS**." (Get started in 3 steps)
- v3.0.2 (17 Nov): "**Import your PPF, NPS, Sukanya, Senior Citizen and post office scheme statements. Just upload the PDF; password-protected ones work too.**"
- v2.0.38 (18 Oct): "**Statement import shows clearer status messages.**"
- v2.0.35 (9 Oct): "Statement import fixes, plus clearer import status messages."
- v2.0.26 (1 Sept): "When you import your **CAS** statement, you can now pick exactly which asset types to bring in."
- v2.0.38: "A sync icon on each account card shows when an amount is still updating." "Inactive bank accounts and matured FDs drop out of your net worth automatically."

**Why this matters for us (scope risk, flag it in Q&A):** the listing describes PDF import for **CAS and scheme statements** and *linking* for bank accounts. It does
**not** say bank-statement PDFs are accepted. Our prototype's scope is bank statements (the case brief lists "bank, mutual fund, demat" PDFs). Step B below
tells you whether the app accepts our bank-statement PDF at all. If it does not, record the exact message: that is itself a valid observation, and the
deck frames our work as a *proposed* self-check that the same idea extends to CAS/scheme statements.
Also note: the app says password-protected PDFs work; our prototype returns `UNSUPPORTED` for encrypted files (a known gap).

## 3. Files to transfer to your phone (all synthetic, known answers)
The files are on the public repo (raw links open/download directly on a phone; or copy them from `fixtures/` by cable, email or Drive).

| # | File | Raw link | Our prototype's result |
|---|---|---|---|
| 1 | `fixtures/samples/1_clean_statement.pdf` (45 rows) | https://raw.githubusercontent.com/Amaan-Khan-09/WealthNest/main/fixtures/samples/1_clean_statement.pdf | READY |
| 2 | `fixtures/samples/2_amount_mismatch_caught.pdf` (row 4 is 1,000.00 off) | https://raw.githubusercontent.com/Amaan-Khan-09/WealthNest/main/fixtures/samples/2_amount_mismatch_caught.pdf | NEEDS_REVIEW at row 4 |
| 3 | `fixtures/audit/short_statement_synthetic.pdf` (3 rows; opening 10,000.00, closing 12,500.00) | https://raw.githubusercontent.com/Amaan-Khan-09/WealthNest/main/fixtures/audit/short_statement_synthetic.pdf | READY |
| 4 | `fixtures/samples/5_scanned_image_only.pdf` (image only) | https://raw.githubusercontent.com/Amaan-Khan-09/WealthNest/main/fixtures/samples/5_scanned_image_only.pdf | UNSUPPORTED |
| 5 | `fixtures/audit/short_statement_password_protected.pdf` (password `synthetic1`) | local until pushed; regenerate with `python -m bench.make_audit_fixtures` | UNSUPPORTED (encrypted) |

All are invented ("Synthetic sample ... Not a real bank statement"). Never upload anything real.

## 4. Run sheet (≈30 min). Record the exact words on screen
**A. Find statement import (5 min).** Sign in. Where is import: onboarding, the Add button, an account card, Settings? How many taps from home? What does the screen say about supported documents, banks, size, passwords?
**B. Clean file (8 min).** Import file 1. Is a bank-statement PDF accepted? Exact status/message; progress; what you can inspect afterwards (dates, transactions, balances, opening/closing); did family net worth change.
**C. Edge cases (8 min).** Import file 3 (short), then file 4 (image-only), then file 2 (mismatch) if the app took file 1. Exact messages and recovery options (retry, edit, manual add, contact support).
**D. Password + review (6 min).** Import file 5 and enter `synthetic1`: does it work? Anywhere a review/edit step for imported data? Anything flagged "needs attention"? What happens if you import the same file twice?
**E. Wrap-up (3 min).** What confused you, what felt slow, what would make you return.

If a step is gated (OTP, account linking, a document-type gate), write the **exact gate and screen** and stop there; do not describe what is behind it.

## 5. What to send me
For **each of up to three observations**:

| Field | Write |
|---|---|
| 1. Path | e.g. Home → Add → Import statement |
| 2. Action + file | e.g. selected file 2 |
| 3. What appeared (verbatim) | the exact message or status text |
| 4. Why it matters for someone importing a family member's statement | one sentence |
| 5. Screenshot | blurred; name `obs1.png` etc. |
| Label | `[OBSERVED]` for what you saw; `[HYPOTHESIS]` for inference about internals |

Send them as text plus the sanitized screenshots (no names, phone numbers, account numbers, balances). I will then update `AUDIT_EVIDENCE.md`, the deck
(slide 2 and the demo choice), the 100-word Unstop observations, and rebuild the PDF. Until then every observation slot stays PENDING.

## 6. Demo choice: current decision and how evidence would change it
Current: **keep the row-4 (1,000.00) mismatch demo**, labelled *proposed improvement, synthetic*. The store listing alone does not show how the app reacts to a wrong or partial import, so nothing yet argues for a different lead.

| If the app… | Then lead with… |
|---|---|
| accepts the mismatched file with no warning | sample 2 as is: "same file, stopped, with the exact row" |
| rejects bank-statement PDFs outright (CAS/scheme only) | still sample 2, reframed: "the same self-check idea for bank statements the brief lists; the app's own scope is CAS/schemes" and say so plainly |
| shows a vague status/error | sample 2 + review card: "say *which row* and why" |
| shows extracted rows but no flags | the flagged review card |
| supports password PDFs and we do not | keep it as a stated gap |
