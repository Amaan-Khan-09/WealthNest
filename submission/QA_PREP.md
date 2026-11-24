# 30-minute presentation plan and likely Q&A

## Timing (30 min)
| Min | Section | Slides |
|---|---|---|
| 0–3 | Problem, the question, what is **not** claimed | 1–2 |
| 3–6 | Scope decision and architecture | 3–4 |
| 6–12 | **Live demo**: clean → caught → review → fix (see `DEMO_SCRIPT.md`) | 5 |
| 12–16 | What the checks can/cannot see | 6 |
| 16–21 | Benchmark design and results | 7–8 |
| 21–25 | Limitations and post-lock changes (say them first) | 9 |
| 25–28 | Rollout, pilot, hypotheses | 10 |
| 28–30 | Buffer / close | 11 |

**Individual contribution:** `PENDING: to be written only after you confirm what you personally built, decided and tested.`
(Nothing about contribution is drafted on purpose.)

## Likely questions, with answers you can defend

**1. The generator and the parser are both yours. Isn't this circular?**
Partly, and I say so. What limits it: the ground-truth ledger is computed in exact `Decimal` before any rendering and rendered with
reportlab, while the parser uses PyMuPDF on the result, so the parser never sees the truth. The holdout uses four layouts I did not
develop against, and the fixtures and code are hash-locked. What it cannot do: tell us how real bank PDFs behave. Seven invented layouts
are not a sample of reality. The pilot plan exists to close that gap.

**2. 28/28 flagged: do you believe that generalises?**
No. It says: "no misses observed in 28 problem documents", with a 95% interval of 88–100%. The more useful statement is structural:
every injected arithmetic error was caught 300/300 in the validator-only test, and the cases arithmetic cannot see (descriptions,
in-order dates, cancelling errors with no running balance) are listed with 0% next to them.

**3. Your first baseline scored 9/100. Why should I trust the comparison?**
That draft was a strawman: it assigned narration words to numeric columns. I replaced it with a baseline that classifies money tokens first,
then fixed a second bug (it read the "D" in "JOSEPH D SOUZA" as a Dr/Cr marker) found on *dev* data. Both changes are disclosed in
`bench/LOCK.json`. The v1 baseline was written after I had seen the naive baseline's holdout score, so its holdout number is not blind. The headline
that does not depend on the baseline is the check itself: 0 wrong imports of 28 problem documents, 100% detection in the validator-only test.

**4. Isn't arm 3b just tuning on the test set?**
Yes: that is why the headline is the *locked* arm 3 (87/100), and 3b (93/100) is labelled optimistic. 3b exists to show the two failures
were real bugs rather than noise.

**5. Why not use an LLM or OCR?**
Deliberate. No API keys needed, deterministic output I can explain line by line, and the brief's emphasis is *catching* errors. A model could be
added as a candidate generator behind the same validation gate; it would need its own benchmark. OCR was not available/reproducible here, so
image-only files return `UNSUPPORTED`.

**6. What if the bank's own statement is wrong?**
Then the document is inconsistent with itself and the checks flag it: that is the `src_*` categories (missing row, duplicated row, altered amount). A parser
cannot repair a source defect, only a human can, with the evidence crop.

**7. Why did the recovery step fix those OCR tokens: isn't that guessing?**
It only repairs when (a) the token was unreadable or the document already shows OCR damage, and (b) the printed balances before and after the row
confirm exactly one candidate. A clean-text amount that disagrees with its balances is *not* overridden. Every repair is logged and the status is
`READY_AUTOFIXED`, not `READY`.

**8. Locked run: 13 of 17 auto-corrections were layout F direction repairs. Doesn't that make recovery look better than it is?**
That is exactly the caveat: recovery masked a parser bug. Correct, accepted, but it is not "free accuracy". After the fix 7 documents are
auto-corrected, all from genuine OCR damage and all correct.

**9. Layout H: all 16 false alarms. Isn't that a design failure?**
It is a policy trade-off. Without opening and closing balances the first row cannot be verified, so nothing is called "ready". Alternatives: allow
"ready, first row unverified" with a visible tag; or ask the user for the opening balance. I chose strict because a silent import is the costlier error.

**10. What about security of untrusted PDFs?**
Caps on size, pages and words per page; encrypted files rejected; nothing is executed. In-process parsing is still a risk. Production should isolate in a
sandboxed worker with timeouts and memory limits. The prototype does not.

**11. How would this plug into Account Aggregator?**
AA delivers structured data directly; PDFs are the fallback for what AA does not cover. `export.to_aa_like()` emits an illustrative record in the shape of the
public ReBIT deposit schema so downstream code is source-agnostic. Field names/enums are my assumption; I have not seen WealthNest's schema and would verify against
ReBIT v2.0.0.

**12. Why `Decimal`, why Indian grouping tests?**
Floats can silently change paise; reconciliation relies on exact equality. `12,34,567.89` must parse the same as `1234567.89`, and a malformed group (a dropped
digit) is itself a signal.

**13. Mutual-fund/demat statements?**
Out of scope: they lack the built-in redundancy to self-check. A CAS has per-folio unit/NAV/amount relationships that could carry a similar gate; that is the natural next step.

**14. What did you see in the live app?** `PENDING: answer from your audit.` Do not answer from assumption: say "I observed X; I infer Y" and label which is which.

**15. What would you do first at WealthNest?**
Shadow-mode the guard on consented uploads for two weeks, human-audit a stratified sample, and decide on thresholds before looking at results.

## One-liners to keep handy
- "I report problem-document recall with denominators: 28/28, interval 88–100."
- "Detection alone sends 89% to review; extraction is what makes it affordable."
- "The checks are blind to descriptions and in-order dates, and to cancelling errors with no running balance. Measured, not hidden."
