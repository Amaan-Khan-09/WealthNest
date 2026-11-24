# 30-minute live-app walkthrough (statement import)

Why: the judging criteria give **30%** to insight "only someone who used WealthNest would make". This repo
cannot supply that: only you can, by using the app. Do this once, take notes, then fill in
`AUDIT_EVIDENCE.md`.

**Ground rules**
- Use a **demo mode or synthetic statements only**. Never upload a real statement, never connect a real account.
  The brief itself says the demo-mode question is still "to confirm": check, or email info@wealthnest.ai.
- Blur personal details in every screenshot. Do not paste real account numbers or balances anywhere.
- You may use the synthetic PDFs in `fixtures/samples/` and `fixtures/audit/` as the file to import. That gives a known-answer test. The condensed run sheet is in [`AUDIT_HANDOFF.md`](AUDIT_HANDOFF.md).
- Write what you **saw**, not what you assume happens internally. Anything about internals is a hypothesis.

## Part 1: before import (5 min)
- [ ] Where does the statement-import entry point live? How many taps from the home screen?
- [ ] What file types does the picker offer? Is a PDF accepted? Is there a size or page limit message?
- [ ] Is there any guidance on *which* statements work (bank names, date ranges, password-protected files)?

## Part 2: import (10 min)
Import `fixtures/samples/1_clean_statement.pdf`, then `2_amount_mismatch_caught.pdf`, then
`5_scanned_image_only.pdf`.
- [ ] Progress feedback: spinner, percentage, time taken?
- [ ] **Visible error messages**: exact wording for each file. Screenshot them.
- [ ] Did the app accept the synthetic file at all? If rejected, what reason did it give?
- [ ] Was any member / account / bank selection required before or after import?

## Part 3: post-import review (10 min)
- [ ] Is the extracted data shown to you for review **before** it affects net worth, or does it land directly?
- [ ] Can you **inspect** individual extracted transactions? Can you **correct** a wrong amount or date?
- [ ] Is there any indication of confidence, "needs attention", or reconciliation (opening/closing)?
- [ ] For the mismatched sample: did anything flag it? What did the family net worth do?
- [ ] What happens on re-import of the same statement (duplicates)?
- [ ] Which Smart Insights, if any, depend on the imported data?

## Part 4: what made you want to come back / what confused you (5 min)
Three bullet points each. The Unstop form asks for your **top 3 observations (≤ 100 words)**.

## How to record each observation
Screen/step · what you saw (verbatim text where possible) · consequence for a family managing several accounts ·
screenshot filename · `[OBSERVED]` or `[HYPOTHESIS]`.
