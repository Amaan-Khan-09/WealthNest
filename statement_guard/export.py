"""Structured exports. Money is always written as exact decimal strings."""
from __future__ import annotations

import csv
import io
import json

from .models import Statement


def to_json(stmt: Statement) -> str:
    return json.dumps(stmt.model_dump(mode="json"), indent=2, ensure_ascii=False)


def to_csv(stmt: Statement) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["row", "page", "date", "description", "debit", "credit", "balance", "flags"])
    by_row: dict[int, list[str]] = {}
    for f in stmt.flags:
        if f.row_idx is not None:
            by_row.setdefault(f.row_idx, []).append(f.code)
    for t in stmt.txns:
        w.writerow([t.idx + 1, t.page, t.date.isoformat() if t.date else "", t.description,
                    t.debit if t.debit is not None else "", t.credit if t.credit is not None else "",
                    t.balance if t.balance is not None else "", ";".join(by_row.get(t.idx, []))])
    return buf.getvalue()


def to_aa_like(stmt: Statement) -> dict:
    """Illustrative canonical shape modelled on the public ReBIT/Account Aggregator deposit schema
    (Summary.currentBalance, Transactions[].narration/valueDate/reference). Field names and the
    DEBIT/CREDIT values are our assumption, not WealthNest's internal schema; verify against ReBIT v2.0.0."""
    return {
        "source": "statement_pdf",
        "importStatus": stmt.status.value,
        "summary": {"openingBalance": str(stmt.opening) if stmt.opening is not None else None,
                    "currentBalance": str(stmt.closing) if stmt.closing is not None else None},
        "transactions": [{
            "type": "DEBIT" if t.debit is not None else "CREDIT",
            "amount": str(t.debit if t.debit is not None else t.credit) if (t.debit or t.credit) is not None else None,
            "currentBalance": str(t.balance) if t.balance is not None else None,
            "valueDate": t.date.isoformat() if t.date else None,
            "narration": t.description, "reference": t.ref,
            "provenance": {"page": t.page, "sourceText": t.source_text},
        } for t in stmt.txns],
    }
