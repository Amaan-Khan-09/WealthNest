"""Validator tests on extracted *records* (no PDFs): inject known errors and check what is/ isn't caught.

These are deliberately separate from the PDF-level benchmark: they test the checks in isolation,
including the error classes that arithmetic cannot catch."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from statement_guard.models import Status, Statement, Txn
from statement_guard.validate import validate

D = Decimal


def make(n=12, with_balance=True) -> Statement:
    bal = D("100000.00")
    opening = bal
    rows = []
    d0 = date(2026, 1, 1)
    for i in range(n):
        if i % 3 == 0:
            deb, cred = None, D("2500.50") + i
            bal += cred
        else:
            deb, cred = D("1234.25") + i * 7, None
            bal -= deb
        rows.append(Txn(idx=i, page=1, date=d0 + timedelta(days=i), description=f"ROW {i}", debit=deb, credit=cred,
                        balance=bal if with_balance else None, raw={"balance": "x"} if with_balance else {}))
    return Statement(opening=opening, closing=bal, txns=rows)


def reindex(s: Statement) -> Statement:
    for i, t in enumerate(s.txns):
        t.idx = i
    return s


def codes(s):
    return {f.code for f in s.errors()}


def test_clean_statement_is_ready():
    s = validate(make())
    assert s.status == Status.READY and s.verification_level == "full_chain"


def test_dropped_row_localised_to_the_row_after_the_gap():
    s = make()
    del s.txns[5]
    s = validate(reindex(s))
    assert s.status == Status.NEEDS_REVIEW
    assert "balance_break" in codes(s) and "reconcile" in codes(s)
    assert min(f.row_idx for f in s.errors() if f.code == "balance_break") == 5


def test_duplicated_row_is_flagged_as_possible_duplicate():
    s = make()
    s.txns.insert(4, s.txns[3].model_copy(deep=True))
    s = validate(reindex(s))
    br = [f for f in s.errors() if f.code == "balance_break"]
    assert br and "duplicated" in br[0].message


def test_flipped_direction_flagged_with_hint():
    s = make()
    t = s.txns[2]
    t.debit, t.credit = None, t.debit
    s = validate(s)
    br = [f for f in s.errors() if f.code == "balance_break" and f.row_idx == 2]
    assert br and "flipped" in br[0].message


def test_single_digit_amount_error_caught_and_localised():
    s = make()
    s.txns[7].debit += D("90.00")
    s = validate(s)
    assert s.status == Status.NEEDS_REVIEW
    assert any(f.code == "balance_break" and f.row_idx == 7 for f in s.errors())


def test_without_running_balance_totals_still_catch_a_single_error():
    s = make(with_balance=False)
    s.txns[4].debit += D("10.00")
    s = validate(s)
    assert s.verification_level == "totals_only" and "reconcile" in codes(s)


def test_without_running_balance_offsetting_errors_survive():
    """Documented limitation: two errors that cancel pass an opening/closing check."""
    s = make(with_balance=False)
    s.txns[4].debit += D("10.00")
    s.txns[5].debit -= D("10.00")
    s = validate(s)
    assert s.status == Status.READY


def test_with_running_balance_the_same_offsetting_errors_are_caught():
    s = make()
    s.txns[4].debit += D("10.00")
    s.txns[5].debit -= D("10.00")
    assert validate(s).status == Status.NEEDS_REVIEW


def test_description_and_in_order_date_errors_survive_arithmetic():
    """Documented limitation: arithmetic cannot see wrong text or a wrong-but-ordered date."""
    s = make()
    s.txns[3].description = "WRONG NARRATION"
    s.txns[3].date = s.txns[3].date + timedelta(hours=0)
    s.txns[4].date = s.txns[3].date          # still non-decreasing
    assert validate(s).status == Status.READY


def test_date_going_backwards_is_flagged():
    s = make()
    s.txns[6].date = date(2025, 12, 1)
    assert "date_order" in codes(validate(s))


def test_page_furniture_inside_description_is_flagged():
    s = make()
    s.txns[-1].description += " Page 2 of 2 Synthetic sample"
    assert "layout_bleed" in codes(validate(s))


def test_unanchored_statement_is_never_ready():
    s = make()
    s.opening = None
    s = validate(s)
    assert s.status == Status.NEEDS_REVIEW and "unanchored" in codes(s)


def test_declared_totals_mismatch():
    s = make()
    s.declared_total_debits = D("1.00")
    assert "declared_total_mismatch" in codes(validate(s))


def test_empty_statement_needs_review():
    assert validate(Statement(opening=D(0), closing=D(0))).status == Status.NEEDS_REVIEW


@pytest.mark.parametrize("n", [1, 2])
def test_tiny_statements(n):
    assert validate(make(n)).status == Status.READY
