# End-to-end review: what was verified, what was found, what changed

## Verified
| Check | Result |
|---|---|
| Fresh `git clone` of the pushed repo → `pytest`, `bench.make_fixtures --check`, CLI | all pass from a clean checkout |
| Static analysis (`ruff`: pyflakes, bugbear, simplify, pyupgrade) | no logic bugs; dead variables removed |
| Fuzz: 162 corrupted / truncated / adversarial PDFs × 5 modes (810 runs) | found 1 crash (below); slowest run 0.11 s |
| Scored fuzz: 792 byte-mutated statements vs ground truth | **0 imported-but-wrong**; 270 routed to `UNSUPPORTED`, 389 to review |
| Benchmark regression after every change: dev (56) + holdout (100) × 5 arms = 780 case/arm results | **0 differences** vs the saved results, incl. the locked arm |
| Real Streamlit server | `/_stcore/health` and `/` return 200; Streamlit test harness drives samples, reviewer fix, pipeline switch, deep link |

## Found and fixed
| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | A damaged PDF (`malformed page tree`) raised an uncaught PyMuPDF error from `process()` | **High**: a hostile/corrupt upload could crash the caller | `process()` is fail-safe: any error → `UNSUPPORTED`, never a crash, never `READY`. Regression tests |
| 2 | CSV export wrote untrusted descriptions verbatim: `=HYPERLINK(...)` would execute when opened in Excel/Sheets | **Medium** (spreadsheet formula injection) | cells starting with `= + - @ tab CR` are prefixed with `'`; test |
| 3 | `to_aa_like()` exported a `0.00` amount as `null` (falsy `Decimal`) | Low | explicit `is not None` checks; test |
| 4 | A transaction whose narration reads "ACCOUNT CLOSING BALANCE TRANSFER" was swallowed as the statement's closing row, silently dropping a transaction and setting a wrong closing | **Medium** | `fixes=True` only: lines carrying a debit/credit amount stay transactions; summary finder skips date-led lines |
| 5 | Short statements (a column with only 1–2 entries) lost their amount columns (needs ≥3 per column) → false review | Medium (false alarms on low-activity accounts; failed safe) | `fixes=True` only: when the header promises more numeric columns than were found, relax the minimum, ignoring label lines |
| 6 | Flag text echoed PDF content and was rendered as Markdown in the UI | Low | rendered as plain text |
| 7 | Reviewer had to compute the correct amount by hand | UX | `balance_break` flags now carry `balances_imply`; the review card shows it as a hint |
| 8 | CLI traceback on a missing file; deck builder only found Windows browsers; widget key used `id(obj)` | Low | friendly error; macOS/Linux browser discovery; revision counter |
| 9 | No CI | Process | `.github/workflows/ci.yml` runs tests + lock check (**not yet run on GitHub**) |

Items 4 and 5 are gated behind `fixes=True` so the benchmark's locked arm (`full`) stays exactly as locked. They do **not** change any benchmark number
because the fixtures contain no such edge cases; they are covered by unit tests instead. All changes are listed in `bench/LOCK.json → post_lock_changes`.

## Known gaps left as they are (not fixed)
- Statements with no printed opening/closing are always held for review (layout H, 16 false alarms): a policy trade-off.
- No OCR; no sandboxing of the in-process PDF parser; no per-file timeout (worst observed 0.11 s, but a pathological PDF could be slower).
- Right-hand "balance suffix" forms like `5,000.00-` and multi-line header cells are not parsed (they fail safe into review).
- Benchmark is synthetic; real bank layouts remain unmeasured.
