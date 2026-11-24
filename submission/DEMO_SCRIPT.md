# Demo script (about 4 minutes) and speaker notes

**Framing (say this first).** "This is a *proposed improvement*, shown on synthetic statements. I am not claiming how the live WealthNest
importer behaves." Once your audit observations exist, replace this with: "In the app I saw X; here is what a self-checking import would do instead."

**Why sample 2 is the demo case (until you have audit evidence):** it is the cleanest picture of the failure that matters for a family importing
someone else's statement, a *silently wrong number*, and it shows detection (row 4, 1,000.00 off), evidence (red box on the source page),
and recovery (edit, re-validate) in one minute. If the audit shows the app rejects PDFs with a generic error, keep sample 2 but lead with
"say which row"; if it shows no review step, lead with the review card. See the mapping table in `docs/audit/AUDIT_HANDOFF.md`.

**Optional edge case (30 s):** `fixtures/audit/short_statement_synthetic.pdf` (3 rows). The default pipeline reads it as READY; the benchmark-locked
`full` mode falls back to review (the short-statement fix is in `full_fixed`).

**Setup:** `streamlit run app/streamlit_app.py` → open `http://localhost:8501`. Keep **Pipeline = full_fixed**. Sidebar buttons load
the sample statements (all synthetic). Deep links: `?sample=1` … `?sample=5`.

## 0:00 Clean statement (sample 1)
Click **Clean statement**. Banner: **READY TO IMPORT**. Point at: 45 rows, opening and closing found, verification "row-by-row".
Say: "Every row's balance follows from the previous one, and opening + credits − debits equals closing. Nothing was changed."
Tab *Why this status*: "All checks passed."

## 1:00 Error caught before import (sample 2)
Click **Amount mismatch caught**. Banner: **NEEDS REVIEW. Not import-ready.**
- *Why this status*: two checks: row 4 "balance moved by 77,036.78 but this row accounts for 76,036.78 (unexplained 1,000.00)", and the
  whole-statement reconcile "off by 1,000.00".
- Say: "The printed statement is inconsistent with itself. A better parser could not fix that; a person has to look. A parser with no
  checks would have imported it; flip **Pipeline → baseline** to show: READY, nothing flagged." (Flip back to full_fixed.)
- *Export* tab: import export is **disabled**; only diagnostics.

## 2:00 Review flow
Tab **Review & fix**. Show the red box on the source page crop for row 4. Edit that row's amount to the value the balances imply
(77,036.78), click **Re-validate**. Banner: **READY TO IMPORT (human-reviewed)**; *Reviewer edits* lists the change; Export is now enabled.
Say: "A reviewer cannot skip the checks: the edit goes back through the same validation."

## 3:00 The other two statuses (30 s each)
- **Noisy text (sample 4):** banner amber, **READY with auto-corrections**: eight tokens were damaged (3 balances with a dropped digit, 5 letter-for-digit swaps); each repair lists its
  evidence ("balance chain holds on both sides"). "Auto-fix only when two independent facts agree, and it's logged."
- **Scanned image (sample 5):** **UNSUPPORTED**: "No OCR, so we say so rather than guess."

## Command-line equivalent
```
python -m statement_guard.cli fixtures/samples/1_clean_statement.pdf
python -m statement_guard.cli fixtures/samples/2_amount_mismatch_caught.pdf --json out.json --csv out.csv
```
Exit code is 0 for importable, 2 otherwise.

## If something goes wrong live
- Streamlit not loading: use the CLI commands above; the output is the same result object.
- A judge uploads their own PDF: fine if synthetic; say that real bank layouts are unmeasured and the likely outcome is review, not a wrong import.
