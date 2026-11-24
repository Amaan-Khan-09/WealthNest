"""Scoring: align extracted rows to the printed ground truth, count errors, summarise detection quality."""
from __future__ import annotations

import math
import re
from decimal import Decimal

from statement_guard.models import IMPORTABLE, Statement

D = Decimal


def _dec(x):
    return None if x is None else D(x)


def _ws(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def _tsigned(r: dict) -> Decimal:
    return (_dec(r["credit"]) or D(0)) - (_dec(r["debit"]) or D(0))


def _esigned(t) -> Decimal | None:
    return t.signed


def align(truth_rows: list[dict], ext_rows: list, has_balance: bool) -> list[tuple[int, int]]:
    """Order-preserving alignment; a pair needs >=2 of the key fields (date, signed amount, balance) to agree."""
    n, m = len(truth_rows), len(ext_rows)

    def score(i: int, j: int) -> int:
        tr, er = truth_rows[i], ext_rows[j]
        s = int(er.date is not None and er.date.isoformat() == tr["date"])
        s += int(_esigned(er) is not None and _esigned(er) == _tsigned(tr))
        if has_balance:
            s += int(er.balance is not None and er.balance == _dec(tr["balance"]))
        return s

    need = 2
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best = max(dp[i + 1][j], dp[i][j + 1])
            sc = score(i, j)
            if sc >= need:
                best = max(best, dp[i + 1][j + 1] + sc)
            dp[i][j] = best
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        sc = score(i, j)
        if sc >= need and dp[i][j] == dp[i + 1][j + 1] + sc:
            pairs.append((i, j))
            i += 1
            j += 1
        elif dp[i][j] == dp[i + 1][j]:
            i += 1
        else:
            j += 1
    return pairs


def score_doc(truth: dict, stmt: Statement) -> dict:
    rows_t = truth["printed_rows"]
    has_bal = truth["has_balance"]
    ext = stmt.txns
    pairs = align(rows_t, ext, has_bal)
    pmap = {i: j for i, j in pairs}
    f = {"date": 0, "amount": 0, "balance": 0, "description": 0}
    bad_ext_idx: set[int] = set()
    fin_wrong_truth = 0
    for i, tr in enumerate(rows_t):
        j = pmap.get(i)
        if j is None:
            fin_wrong_truth += 1
            continue
        e = ext[j]
        ok_date = e.date is not None and e.date.isoformat() == tr["date"]
        ok_amt = (e.debit == _dec(tr["debit"])) and (e.credit == _dec(tr["credit"]))
        ok_bal = (not has_bal) or (e.balance == _dec(tr["balance"]))
        ok_desc = _ws(e.description) == _ws(tr["description"])
        f["date"] += ok_date
        f["amount"] += ok_amt
        f["balance"] += ok_bal
        f["description"] += ok_desc
        if not (ok_date and ok_amt and ok_bal):
            fin_wrong_truth += 1
            bad_ext_idx.add(j)
    matched_ext = set(pmap.values())
    extra = [j for j in range(len(ext)) if j not in matched_ext]
    missed = [i for i in range(len(rows_t)) if i not in pmap]
    # indices in the extracted list that sit next to a missing row
    for i in missed:
        pos = sum(1 for (ti, tj) in pairs if ti < i)
        bad_ext_idx.update({pos - 1, pos})
    bad_ext_idx.update(extra)
    # source-defect location (index into printed rows, ~ same index in a faithful extraction)
    d = truth.get("source_defect")
    if d:
        k = d["row"]
        bad_ext_idx.update({k - 1, k, k + 1} if d["type"] != "missing_row" else {k - 1, k})
    opening_ok = stmt.opening == _dec(truth["opening"]) if truth["summary_printed"] else None
    closing_ok = stmt.closing == _dec(truth["closing"]) if truth["summary_printed"] else None
    anchor_ok = (opening_ok is not False) and (closing_ok is not False)
    # a summary the layout never prints cannot be 'wrong'; the unanchored flag handles that case
    fin_error = bool(fin_wrong_truth or extra or not anchor_ok)
    desc_error = f["description"] < len(rows_t) - len(missed) or fin_error
    flagged = stmt.status.value in ("NEEDS_REVIEW", "UNSUPPORTED")
    flagged_rows = {fl.row_idx for fl in stmt.flags if fl.severity == "error" and fl.row_idx is not None}
    positive = fin_error or truth["expected_review"]
    loc_hit = None
    if flagged and positive and flagged_rows:
        loc_hit = any(abs(fr - b) <= 1 for fr in flagged_rows for b in bad_ext_idx) if bad_ext_idx else None
    return {
        "n_truth": len(rows_t), "n_extracted": len(ext), "matched": len(pairs),
        "missed": len(missed), "extra": len(extra), "fields": f,
        "opening_ok": opening_ok, "closing_ok": closing_ok,
        "fin_error": fin_error, "any_error": desc_error, "positive": positive,
        "status": stmt.status.value, "flagged": flagged, "accepted": stmt.status in IMPORTABLE,
        "flag_codes": sorted({fl.code for fl in stmt.flags if fl.severity == "error"}),
        "n_repairs": len(stmt.repairs), "repair_kinds": sorted({r.kind for r in stmt.repairs}), "loc_hit": loc_hit, "runtime_ms": round(stmt.runtime_ms, 1),
        "layout": truth["layout"], "has_balance": truth["has_balance"], "category": truth["category"], "split": truth["split"],
        "expected_review": truth["expected_review"], "image_only": truth["image_only"],
        "bad_rows": sorted(b for b in bad_ext_idx if b >= 0),
    }


# ----------------------------------------------------------------------------- aggregation
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else float("nan")), "ci95": [lo, hi]}


def summarize(scores: list[dict]) -> dict:
    n = len(scores)
    nrows = sum(s["n_truth"] for s in scores)
    out: dict = {"docs": n, "truth_rows": nrows}
    out["doc_exact_financial"] = rate(sum(not s["fin_error"] for s in scores), n)
    out["doc_exact_all_fields"] = rate(sum(not s["any_error"] for s in scores), n)
    for fld in ("date", "amount", "balance", "description"):
        sel = [s for s in scores if fld != "balance" or s["has_balance"]]
        den = sum(s["n_truth"] for s in sel)
        num = sum(s["fields"][fld] for s in sel)
        out[f"field_{fld}"] = rate(num, den)
    out["rows_missed"] = rate(sum(s["missed"] for s in scores), nrows)
    out["rows_extra"] = {"k": sum(s["extra"] for s in scores), "n": nrows}
    pos = [s for s in scores if s["positive"]]
    neg = [s for s in scores if not s["positive"]]
    tp = sum(s["flagged"] for s in pos)
    fp = sum(s["flagged"] for s in neg)
    out["positives"] = len(pos)
    out["negatives"] = len(neg)
    out["recall"] = rate(tp, len(pos))
    out["precision"] = rate(tp, tp + fp)
    out["false_acceptance"] = rate(sum(s["accepted"] for s in pos), len(pos))
    out["false_alarm"] = rate(fp, len(neg))
    out["review_rate"] = rate(sum(s["flagged"] for s in scores), n)
    out["silent_wrong_imports"] = sum(s["accepted"] for s in pos)
    loc = [s["loc_hit"] for s in scores if s["loc_hit"] is not None]
    out["localisation"] = rate(sum(loc), len(loc))
    acc = [s for s in scores if s["accepted"]]
    out["accepted_docs"] = len(acc)
    out["accepted_correct"] = rate(sum(not s["fin_error"] and not s["expected_review"] for s in acc), len(acc))
    af = [s for s in scores if s["status"] == "READY_AUTOFIXED"]
    out["autofixed"] = rate(sum(not s["fin_error"] and not s["expected_review"] for s in af), len(af))
    rt = sorted(s["runtime_ms"] for s in scores)
    out["runtime_ms_median"] = rt[len(rt) // 2] if rt else None
    out["runtime_ms_p95"] = rt[int(0.95 * (len(rt) - 1))] if rt else None
    return out


def by_group(scores: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for s in scores:
        groups.setdefault(s[key], []).append(s)
    res = {}
    for g, ss in sorted(groups.items()):
        pos = [s for s in ss if s["positive"]]
        res[g] = {
            "n": len(ss),
            "fin_exact": sum(not s["fin_error"] for s in ss),
            "flagged": sum(s["flagged"] for s in ss),
            "positives": len(pos),
            "pos_flagged": sum(s["flagged"] for s in pos),
            "pos_accepted": sum(s["accepted"] for s in pos),
        }
    return res
