# App audit evidence: PENDING (needs Mohammed Amaan Khan)

> **Attempt log.** 2026-11-25: audit requested; **not performed**. Blockers: the assistant had no browser/device/computer-use tool, and no verified
> official app link was available (brief placeholder `{{App link}}`; web search found only a Product Hunt page for WealthNest.ai and unrelated
> apps with similar names). **Zero observations verified.** See [`AUDIT_HANDOFF.md`](AUDIT_HANDOFF.md) for the exact run sheet and files.

> Nothing in this file is evidence yet. Every row below is an empty slot. The deck and the Unstop form must
> not claim anything about the live app until these are filled with things you actually saw.
> Label each: **[OBSERVED]** (you saw it), **[HYPOTHESIS]** (you infer how it works internally),
> **[PROTOTYPE]** (measured by this repo on synthetic data).

## Audit metadata (fill in)
- Date of audit: `PENDING`
- App version / platform: `PENDING`
- Demo mode available? `PENDING (the brief marks this "to confirm")`
- Files used for import (synthetic only): `PENDING`
- Time spent in app (brief asks ≥ 30 min): `PENDING`

## Observations

| # | Screen / step | What you saw (verbatim) | Consequence for a family with several accounts | Evidence (screenshot file, blurred) | Label |
|---|---|---|---|---|---|
| 1 | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` |
| 2 | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` |
| 3 | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `PENDING` |

## Provisional problem statement (to be confirmed or replaced by the audit)

> A family imports several statements. If one import silently contains a wrong or missing transaction, the
> family-level net worth and every insight built on it is wrong, and nothing tells the user. The prototype asks:
> *can a statement be checked against itself, so that doubtful extractions are stopped and shown to a reviewer
> with evidence, instead of being imported quietly?*

Claims that **need your evidence** before they go in the deck:
1. That WealthNest's import flow accepts statement PDFs at all (vs. only AA / other imports).
2. What the app shows when an import is partial or wrong.
3. Whether users can inspect or correct extracted rows.
4. Anything about which statement types users actually import.

## What the deck says while this is pending
Slide 2 shows `[PENDING: app evidence]` markers, and the prototype is framed as "tested on our own reproduction of
a straightforward parser; live-app behaviour not claimed".
