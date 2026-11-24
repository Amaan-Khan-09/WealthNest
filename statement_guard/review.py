"""Reviewer corrections. A human edit never skips validation: edited statements are re-checked with the
same rules, and only a clean re-validation yields READY_REVIEWED."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from .models import Statement, Txn
from .validate import validate

FIELDS = ("date", "description", "debit", "credit", "balance")


def _is_blank(v) -> bool:
    return (v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, float) and v != v)
            or type(v).__name__ in ("NaTType", "NAType"))


def _to_dec(v) -> Decimal | None:
    if _is_blank(v):
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except InvalidOperation as e:
        raise ValueError(f"not a number: {v!r}") from e


def _same(a, b) -> bool:
    return a == b


def apply_table_edits(stmt: Statement, rows: list[dict], opening=None, closing=None) -> Statement:
    """rows: edited table as dicts with keys date, description, debit, credit, balance and optional `_orig`
    (original row index, None for inserted rows). Returns a re-validated copy."""
    new = stmt.model_copy(deep=True)
    old = {t.idx: t for t in stmt.txns}
    out: list[Txn] = []
    edits: list[str] = []
    seen = set()
    for pos, r in enumerate(rows):
        orig = None if _is_blank(r.get("_orig")) else int(r["_orig"])
        base = old.get(orig) if orig is not None else None
        d = r.get("date")
        if _is_blank(d):
            d = None
        elif isinstance(d, str):
            d = date.fromisoformat(d.strip()[:10])
        elif hasattr(d, "date") and not isinstance(d, date):
            d = d.date()
        elif hasattr(d, "to_pydatetime"):
            d = d.to_pydatetime().date()
        t = Txn(idx=pos, page=base.page if base else (out[-1].page if out else 1), date=d,
                date_text=base.date_text if base else "", description=str(r.get("description") or ""),
                ref=base.ref if base else None, debit=_to_dec(r.get("debit")), credit=_to_dec(r.get("credit")),
                balance=_to_dec(r.get("balance")), source_text=base.source_text if base else "(added by reviewer)",
                bbox=base.bbox if base else None, raw=dict(base.raw) if base else {},
                notes=[] if base is None else [n for n in base.notes])
        if base is None:
            edits.append(f"row {pos + 1}: inserted by reviewer")
        else:
            seen.add(orig)
            for f in FIELDS:
                if not _same(getattr(base, f), getattr(t, f)):
                    edits.append(f"row {pos + 1}: {f} {getattr(base, f)!s} -> {getattr(t, f)!s}")
                    if f in ("debit", "credit", "balance"):
                        t.notes = [n for n in t.notes if not n.startswith(f"{f}:") and n != "direction_unknown"]
                    if f in ("debit", "credit"):
                        t.notes = [n for n in t.notes if n != "direction_unknown"]
        # a value typed by the reviewer clears parse notes for that field
        if t.debit is not None or t.credit is not None:
            t.notes = [n for n in t.notes if n != "direction_unknown" and not n.startswith(("debit:", "credit:", "amount:"))]
        if t.balance is not None:
            t.notes = [n for n in t.notes if not n.startswith("balance:")]
        out.append(t)
    for i in old:
        if i not in seen:
            edits.append(f"row {i + 1}: deleted by reviewer")
    new.txns = out
    if opening is not None and opening != stmt.opening:
        edits.append(f"opening balance {stmt.opening} -> {opening}")
        new.opening = opening
    if closing is not None and closing != stmt.closing:
        edits.append(f"closing balance {stmt.closing} -> {closing}")
        new.closing = closing
    new.reviewer_edits = list(stmt.reviewer_edits) + edits
    new.flags = []
    return validate(new)


def table_rows(stmt: Statement) -> list[dict]:
    return [{"_orig": t.idx, "page": t.page, "date": t.date, "description": t.description,
             "debit": t.debit, "credit": t.credit, "balance": t.balance} for t in stmt.txns]
