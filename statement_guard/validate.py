"""Document-level and row-level consistency checks.

Which check needs what:
  * opening + credits - debits == closing      needs only opening/closing balance (works without a running balance)
  * declared totals == computed totals         needs the statement to print totals
  * balance[i] == balance[i-1] +/- amount[i]   needs a running-balance column (localises the suspect row)
  * date order / missing fields / layout bleed needs nothing
Errors that can still survive: wrong descriptions, wrong dates that stay in order, two offsetting amount errors
when only opening/closing exist, and any error that preserves every printed balance relationship.
"""
from __future__ import annotations

import re
from decimal import Decimal

from .models import Flag, Status, Statement

ZERO = Decimal(0)
BLEED = re.compile(r"page\s*\d+\s*(of|/)\s*\d+|synthetic sample|computer generated|end of statement|"
                   r"statement of account|carried forward|brought forward|\*\*\*")


def _fmt(v: Decimal | None) -> str:
    return "n/a" if v is None else f"{v:,.2f}"


def validate(stmt: Statement) -> Statement:
    s = stmt
    flags: list[Flag] = []
    rows = s.txns
    if s.status == Status.UNSUPPORTED:
        return s
    if not rows:
        flags.append(Flag(code="no_rows", severity="error", message="No transactions could be extracted."))

    layout_has_balance = any("balance" in t.raw or t.balance is not None for t in rows)

    # ---- row-level
    prev_date = None
    for t in rows:
        i = t.idx
        for n in t.notes:
            if "unparseable" in n or "bad_grouping" in n:
                flags.append(Flag(code="unparsed_number", severity="error", row_idx=i,
                                  message=f"Number could not be read reliably ({n}).",
                                  evidence={"source": t.source_text}))
            if n == "direction_unknown":
                flags.append(Flag(code="direction_unknown", severity="error", row_idx=i,
                                  message="Amount found but debit/credit direction is not stated for this row.",
                                  evidence={"source": t.source_text}))
        if t.date is None:
            flags.append(Flag(code="date_missing", severity="error", row_idx=i, message="Date missing or unreadable.",
                              evidence={"source": t.source_text}))
        elif prev_date and t.date < prev_date:
            flags.append(Flag(code="date_order", severity="error", row_idx=i,
                              message=f"Date {t.date} is earlier than the previous row ({prev_date}).",
                              evidence={"source": t.source_text}))
        if t.date:
            prev_date = t.date
        if t.debit is not None and t.credit is not None:
            flags.append(Flag(code="both_directions", severity="error", row_idx=i,
                              message="Both debit and credit are set on one row."))
        pending_num = any(("unparseable" in n or "bad_grouping" in n or n == "direction_unknown")
                          and not n.startswith("balance:") for n in t.notes)
        if t.debit is None and t.credit is None and not pending_num:
            flags.append(Flag(code="amount_missing", severity="error", row_idx=i,
                              message="No debit or credit amount found.", evidence={"source": t.source_text}))
        if BLEED.search(t.description.lower()):
            flags.append(Flag(code="layout_bleed", severity="error", row_idx=i,
                              message="Page header/footer text appears inside this row's description.",
                              evidence={"description": t.description[-80:]}))
        if layout_has_balance and t.balance is None and not any(n.startswith("balance:") for n in t.notes):
            flags.append(Flag(code="balance_missing", severity="error", row_idx=i,
                              message="Running balance missing on this row.", evidence={"source": t.source_text}))

    # ---- chain (needs running balance)
    prev = s.opening
    chain_checked = 0
    for t in rows:
        sg = t.signed
        if t.balance is not None and sg is not None and prev is not None:
            chain_checked += 1
            delta = t.balance - prev
            resid = delta - sg
            if resid != 0:
                hyp = []
                if sg != 0 and resid == -2 * sg:
                    hyp.append("debit/credit direction looks flipped on this row")
                if delta == 0 and sg != 0:
                    hyp.append("possible duplicated row (balance did not move)")
                if not hyp:
                    hyp.append("amount misread, or a row is missing/extra just before this one")
                flags.append(Flag(
                    code="balance_break", severity="error", row_idx=t.idx,
                    message=(f"Balance moved by {_fmt(delta)} but this row accounts for {_fmt(sg)} "
                             f"(unexplained {_fmt(resid)}). " + "; ".join(hyp) + "."),
                    evidence={"prev_balance": str(prev), "printed_balance": str(t.balance),
                              "row_amount_signed": str(sg), "unexplained": str(resid), "source": t.source_text}))
        prev = t.balance
    last_bal = next((t.balance for t in reversed(rows) if t.balance is not None), None)
    if layout_has_balance and s.closing is not None and last_bal is not None and last_bal != s.closing:
        flags.append(Flag(code="closing_vs_last_balance", severity="error", row_idx=rows[-1].idx if rows else None,
                          message=f"Closing balance {_fmt(s.closing)} differs from the last running balance {_fmt(last_bal)}.",
                          evidence={"closing": str(s.closing), "last_balance": str(last_bal)}))

    # ---- document-level
    deb = sum((t.debit or ZERO for t in rows), ZERO)
    cred = sum((t.credit or ZERO for t in rows), ZERO)
    if s.opening is None or s.closing is None:
        missing = [n for n, v in (("opening", s.opening), ("closing", s.closing)) if v is None]
        flags.append(Flag(code="unanchored", severity="error",
                          message=f"Cannot anchor the statement: {' and '.join(missing)} balance not found, "
                                  "so totals cannot be reconciled."))
    else:
        diff = s.opening + cred - deb - s.closing
        if diff != 0:
            flags.append(Flag(code="reconcile", severity="error",
                              message=(f"Opening {_fmt(s.opening)} + credits {_fmt(cred)} - debits {_fmt(deb)} = "
                                       f"{_fmt(s.opening + cred - deb)}, but closing is {_fmt(s.closing)} (off by {_fmt(diff)})."),
                              evidence={"opening": str(s.opening), "credits": str(cred), "debits": str(deb),
                                        "closing": str(s.closing), "diff": str(diff)}))
    for label, declared, computed in (("debits", s.declared_total_debits, deb),
                                      ("credits", s.declared_total_credits, cred)):
        if declared is not None and declared != computed:
            flags.append(Flag(code="declared_total_mismatch", severity="error",
                              message=f"Statement states total {label} {_fmt(declared)} but extracted rows sum to {_fmt(computed)}.",
                              evidence={"declared": str(declared), "computed": str(computed)}))

    # ---- verification level
    if layout_has_balance and s.opening is not None and chain_checked >= max(1, int(0.8 * len(rows))):
        s.verification_level = "full_chain"
    elif s.opening is not None and s.closing is not None:
        s.verification_level = "totals_only"
    else:
        s.verification_level = "none"
    if s.verification_level == "totals_only" and rows:
        flags.append(Flag(code="totals_only", severity="info",
                          message="No running balance to check row by row: only opening/closing totals verified."))

    s.flags = flags
    if s.errors():
        s.status = Status.NEEDS_REVIEW
    elif s.reviewer_edits:
        s.status = Status.READY_REVIEWED
    elif s.repairs:
        s.status = Status.READY_AUTOFIXED
    else:
        s.status = Status.READY
    return s
