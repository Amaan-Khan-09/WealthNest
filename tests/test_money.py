from datetime import date
from decimal import Decimal

from statement_guard.money import fmt_indian, grouping_is_valid, parse_amount, parse_date, repair_ocr_amount


def test_indian_grouping_parsed_exactly():
    a = parse_amount("12,34,567.89")
    assert a.value == Decimal("1234567.89") and a.grouping_ok


def test_western_grouping_also_accepted_but_malformed_is_not():
    assert parse_amount("1,234,567.00").grouping_ok
    assert not parse_amount("14,74,36.99").grouping_ok      # dropped digit in last group
    assert not parse_amount("1,234,50").grouping_ok         # comma where the decimal point should be


def test_suffix_negative_and_currency_forms():
    assert parse_amount("2,03,387.16 Cr").suffix == "Cr"
    assert parse_amount("500.00Dr").suffix == "Dr"
    assert parse_amount("(500.00)").negative
    assert parse_amount("₹ 1,000.50").value == Decimal("1000.50")


def test_reference_numbers_are_not_money_with_decimals():
    a = parse_amount("412345678901")
    assert a is not None and "." not in a.text          # extractor requires decimals; refs never qualify


def test_no_float_rounding():
    assert parse_amount("0.10").value + parse_amount("0.20").value == Decimal("0.30")


def test_ocr_confusables_only_inside_numeric_tokens():
    assert repair_ocr_amount("5OO.OO") == "500.00"
    assert repair_ocr_amount("l,234.5O") == "1,234.50"
    assert repair_ocr_amount("BOSS") is None
    assert repair_ocr_amount("SOS.OO") is None            # no real digit: leave alone
    assert repair_ocr_amount("1,234.50") is None          # already clean


def test_dates_day_first():
    assert parse_date("05/01/26") == date(2026, 1, 5)
    assert parse_date("05 Jan 2026") == date(2026, 1, 5)
    assert parse_date("30-Apr-2026") == date(2026, 4, 30)
    assert parse_date("2026-01-05") == date(2026, 1, 5)
    assert parse_date("31/02/2026") is None
    assert parse_date("Narration") is None


def test_fmt_indian_roundtrip():
    for v in ["0.05", "999.99", "1000.00", "12345.60", "1234567.50", "123456789.01"]:
        d = Decimal(v)
        assert parse_amount(fmt_indian(d)).value == d
    assert fmt_indian(Decimal("1234567.5")) == "12,34,567.50"
    assert grouping_is_valid("12,34,567")
