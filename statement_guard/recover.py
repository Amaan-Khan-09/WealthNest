"""Bounded, evidence-backed recovery. Nothing here guesses: every repair must be confirmed by an
independent relationship in the document (the printed running balance on both sides, or document-level
reconciliation), and every accepted repair is recorded in ``Statement.repairs`` for audit.

Repairs implemented
  ocr_confusable  'S,OOO.5O' -> '5,000.50' for tokens that failed to parse; accepted only if the balance chain holds
  comma_decimal   '1,234,50' -> '1,234.50'; same acceptance rule
  direction       amount found without Dr/Cr -> try both, keep the one consistent with the printed balances
  column_order    header-free layouts: debit/credit order assumed; swap only if that (alone) makes totals reconcile
  implied_amount / implied_balance
                  digit-level repair (edit distance <= 1) from the balance chain, ONLY on documents whose text
                  layer already shows OCR damage. On clean digital PDFs we trust the printed digits and send
                  mismatches to a human instead of overriding the document.
Not repaired on purpose: missing rows, duplicated rows, altered amounts on clean text layers (source defects).
"""
from __future__ import annotations

import itertools
import re
from decimal import Decimal

from .models import Repair, Statement, Txn
from .money import fmt_indian, parse_amount, repair_ocr_amount

ZERO = Decimal(0)


def _edit_distance_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _base_token(tok: str) -> str:
    return re.sub(r"\s*(dr|cr)\.?$", "", tok.strip(), flags=re.I)


def _candidates(tok: str) -> list[Decimal]:
    base = _base_token(tok)
    cands: list[str] = []
    r = repair_ocr_amount(base)
    if r:
        cands.append(r)
    m = re.match(r"^(\d[\d,]*),(\d{2})$", base)
    if m:
        c = f"{m.group(1)}.{m.group(2)}"
        a = parse_amount(c)
        if a and a.grouping_ok:
            cands.append(c)
    out: list[Decimal] = []
    for c in cands:
        a = parse_amount(c)
        if a and a.grouping_ok and a.value not in out:
            out.append(a.value)
    return out


def _prev_bal(rows: list[Txn], i: int, opening: Decimal | None) -> Decimal | None:
    return rows[i - 1].balance if i > 0 else opening


def _link(rows: list[Txn], i: int, opening: Decimal | None) -> bool | None:
    """True/False if the balance link into row i can be evaluated, else None."""
    if i < 0 or i >= len(rows):
        return None
    t = rows[i]
    p = _prev_bal(rows, i, opening)
    if t.balance is None or t.signed is None or p is None:
        return None
    return t.balance - p == t.signed


def _reconciles(s: Statement) -> bool:
    if s.opening is None or s.closing is None:
        return False
    deb = sum((t.debit or ZERO for t in s.txns), ZERO)
    cred = sum((t.credit or ZERO for t in s.txns), ZERO)
    return s.opening + cred - deb == s.closing


def _log(s: Statement, kind: str, i: int | None, field: str, before: str, after: str, evidence: str) -> None:
    s.repairs.append(Repair(kind=kind, row_idx=i, field=field, before=before, after=after, evidence=evidence))


def recover(stmt: Statement) -> Statement:
    s = stmt.model_copy(deep=True)
    rows = s.txns
    if not rows:
        return s
    _repair_tokens(s)
    _infer_direction(s)
    _fix_assumed_column_order(s)
    noisy = any(("unparseable" in n or "bad_grouping" in n) for t in rows for n in t.notes) or \
        any(r.kind in ("ocr_confusable", "comma_decimal") for r in s.repairs)
    if noisy:
        _implied_repairs(s)
    return s


# ----------------------------------------------------------------------------- 1. unparsed tokens
def _pending_fields(t: Txn) -> list[tuple[str, str]]:
    out = []
    for role in ("debit", "credit"):
        if role in t.raw and getattr(t, role) is None and any(n.startswith(f"{role}:") for n in t.notes):
            out.append((role, role))
    if "amount" in t.raw and t.debit is None and t.credit is None and any(n.startswith("amount:") for n in t.notes):
        d = t.raw.get("_dir")
        if d in ("debit", "credit"):
            out.append(("amount", d))
    if "balance" in t.raw and t.balance is None and any(n.startswith("balance:") for n in t.notes):
        out.append(("balance", "balance"))
    return out


def _set(t: Txn, target: str, v: Decimal | None) -> None:
    setattr(t, target, v)


def _signed_for(target: str, tok: str, v: Decimal) -> Decimal:
    if target == "balance":
        t = tok.strip()
        if re.search(r"dr\.?$", t, re.I) or t.startswith(("-", "(")):
            return -v
    return v


def _prev_trusted(s: Statement, i: int) -> bool:
    return (i == 0 and s.opening is not None) or (i > 0 and _link(s.txns, i - 1, s.opening) is True)


def _token_candidates(s: Statement, i: int, role: str, target: str) -> list[tuple[Decimal, str]]:
    """(value, kind) candidates for one unparsed token. 'implied' means: previous balance + the other fields
    on the row determine the value, and the printed token is within one character of it."""
    rows, t = s.txns, s.txns[i]
    tok = t.raw[role]
    out: list[tuple[Decimal, str]] = []
    for v in _candidates(tok):
        kind = "comma_decimal" if re.match(r"^\d[\d,]*,\d{2}$", _base_token(tok)) else "ocr_confusable"
        out.append((_signed_for(target, tok, v), kind))
    p = _prev_bal(rows, i, s.opening)
    if p is not None and _prev_trusted(s, i):
        implied = None
        if target in ("debit", "credit") and t.balance is not None:
            delta = t.balance - p
            if (target == "debit" and delta < 0) or (target == "credit" and delta > 0):
                implied = abs(delta)
        elif target == "balance" and t.signed is not None:
            implied = p + t.signed
        if implied is not None:
            base = _base_token(tok)
            shown = fmt_indian(abs(implied))
            if _edit_distance_le1(base, shown) or _edit_distance_le1(base.replace(",", ""), shown.replace(",", "")):
                if all(v != implied for v, _ in out):
                    out.append((implied, "implied_balance" if target == "balance" else "implied_amount"))
    return out


def _repair_tokens(s: Statement) -> None:
    rows = s.txns
    unverifiable: list[tuple[int, str, str, Decimal, str]] = []
    for i, t in enumerate(rows):
        pend = _pending_fields(t)
        if not pend:
            continue
        lists = [_token_candidates(s, i, role, target) for role, target in pend]
        if any(not c for c in lists):
            continue
        verifiable = _link(rows, i, s.opening) is not None or t.balance is None
        # balance may itself be pending: evaluate combos with every pending field set
        good = []
        for combo in itertools.product(*lists):
            for (role, target), (v, _) in zip(pend, combo):
                _set(t, target, v)
            a, b = _link(rows, i, s.opening), _link(rows, i + 1, s.opening)
            if a is True and b is not False:
                good.append(combo)
            for role, target in pend:
                _set(t, target, None)
        has_bal_col = "balance" in t.raw
        if has_bal_col and len(good) == 1:
            for (role, target), (v, kind) in zip(pend, good[0]):
                _set(t, target, v)
                t.notes = [n for n in t.notes if not n.startswith(f"{role}:")]
                _log(s, kind, i, target, t.raw[role], str(v),
                     "balance chain holds on both sides of this row after the repair")
        elif not has_bal_col and all(len(c) == 1 for c in lists):
            for (role, target), c in zip(pend, lists):
                unverifiable.append((i, role, target, c[0][0], t.raw[role]))
    if unverifiable:  # no running balance: accept only if document totals reconcile once all are applied
        snap = s.model_copy(deep=True)
        for i, role, target, v, raw in unverifiable:
            _set(rows[i], target, v)
        if _reconciles(s):
            for i, role, target, v, raw in unverifiable:
                rows[i].notes = [n for n in rows[i].notes if not n.startswith(f"{role}:")]
                _log(s, "ocr_confusable", i, target, raw, str(v), "opening + credits - debits now equals closing")
        else:
            s.txns = snap.txns


# ----------------------------------------------------------------------------- 2. direction from balances
def _infer_direction(s: Statement) -> None:
    rows = s.txns
    for i, t in enumerate(rows):
        if "direction_unknown" not in t.notes or "amount_value" not in t.raw:
            continue
        v = Decimal(t.raw["amount_value"])
        ok = []
        for target in ("debit", "credit"):
            setattr(t, target, v)
            a, b = _link(rows, i, s.opening), _link(rows, i + 1, s.opening)
            if a and b is not False:
                ok.append(target)
            setattr(t, target, None)
        if len(ok) == 1:
            setattr(t, ok[0], v)
            t.notes.remove("direction_unknown")
            _log(s, "direction", i, ok[0], "direction not printed", ok[0],
                 "only this direction is consistent with the printed running balances")


# ----------------------------------------------------------------------------- 3. assumed column order
def _fix_assumed_column_order(s: Statement) -> None:
    if not any("order assumed" in n for n in s.layout_notes):
        return
    if s.opening is None or s.closing is None or _reconciles(s):
        return
    for t in s.txns:
        t.debit, t.credit = t.credit, t.debit
    if _reconciles(s):
        _log(s, "column_order", None, "debit/credit", "left=debit, right=credit", "left=credit, right=debit",
             "only the swapped order reconciles opening/closing balances")
    else:
        for t in s.txns:
            t.debit, t.credit = t.credit, t.debit


# ----------------------------------------------------------------------------- 4. digit-level repair on OCR-damaged docs
def _implied_repairs(s: Statement) -> None:
    rows = s.txns
    for i, t in enumerate(rows):
        if _link(rows, i, s.opening) is not False:
            continue
        prev_trusted = (i == 0 and s.opening is not None) or (i > 0 and _link(rows, i - 1, s.opening) is True)
        if not prev_trusted or t.balance is None or t.signed is None:
            continue
        p = _prev_bal(rows, i, s.opening)
        # (a) the amount is wrong, the printed balance is right (confirmed by the next row)
        next_ok = (_link(rows, i + 1, s.opening) is True) if i + 1 < len(rows) else (s.closing == t.balance)
        if next_ok:
            delta = t.balance - p
            same_dir = (delta < 0) == (t.debit is not None) and delta != 0
            old = t.debit if t.debit is not None else t.credit
            if same_dir and old is not None and _edit_distance_le1(f"{old:.2f}", f"{abs(delta):.2f}"):
                field = "debit" if t.debit is not None else "credit"
                setattr(t, field, abs(delta))
                _log(s, "implied_amount", i, field, f"{old:.2f}", f"{abs(delta):.2f}",
                     "previous and next balances agree; amount differs from the balance movement by one character")
            continue
        # (b) the balance is wrong, the amount is right (confirmed by the next row)
        new_bal = p + t.signed
        old_bal = t.balance
        if i + 1 < len(rows) and rows[i + 1].balance is not None and rows[i + 1].signed is not None and \
                rows[i + 1].balance - new_bal == rows[i + 1].signed and \
                _edit_distance_le1(f"{old_bal:.2f}", f"{new_bal:.2f}"):
            t.balance = new_bal
            _log(s, "implied_balance", i, "balance", f"{old_bal:.2f}", f"{new_bal:.2f}",
                 "previous balance + this amount equals the value the next row expects")
