"""Hostile / damaged input and export-safety tests."""
import csv
import io
import random
from datetime import date
from decimal import Decimal

import pymupdf
import pytest
from pymupdf import mupdf

from bench.generator import make_fixture
from bench.metrics import score_doc
from statement_guard import cli, extract, pipeline
from statement_guard.export import csv_safe, to_aa_like, to_csv
from statement_guard.models import Statement, Status, Txn
from statement_guard.pipeline import MODES, process


def test_library_error_while_reading_pages_routes_to_review_not_crash(monkeypatch):
    """Regression: a malformed page tree made PyMuPDF raise FzErrorFormat out of process()."""
    fx = make_fixture("A", 7, "clean")

    def boom(doc):
        raise mupdf.FzErrorFormat("malformed page tree")
    monkeypatch.setattr(pipeline, "is_image_only", boom)
    st = process(fx.pdf, mode="full")
    assert st.status == Status.UNSUPPORTED and not st.importable
    assert "routed to review" in st.flags[0].message


def test_internal_error_in_extraction_fails_safe(monkeypatch):
    fx = make_fixture("A", 7, "clean")
    monkeypatch.setattr(pipeline, "extract_robust", lambda *a, **k: (_ for _ in ()).throw(IndexError("bug")))
    st = process(fx.pdf, mode="full")
    assert st.status == Status.UNSUPPORTED and not st.importable


def test_missing_path_is_unsupported():
    assert process("does/not/exist.pdf").status == Status.UNSUPPORTED


@pytest.mark.parametrize("layout,cat", [("A", "clean"), ("C", "clean"), ("D", "wide_amounts"), ("B", "overdraft")])
def test_random_byte_corruption_never_crashes_and_never_imports_wrong(layout, cat):
    fx = make_fixture(layout, 31, cat)
    rng = random.Random(5)
    for _ in range(25):
        m = bytearray(fx.pdf)
        kind = rng.choice(["flip", "many", "cut", "trunc"])
        if kind == "flip":
            m[rng.randrange(len(m))] = rng.randrange(256)
        elif kind == "many":
            for _ in range(rng.randint(5, 60)):
                m[rng.randrange(len(m))] = rng.randrange(256)
        elif kind == "cut":
            a = rng.randrange(len(m))
            m = m[:a] + m[a + rng.randint(1, 120):]
        else:
            m = m[: rng.randint(10, len(m) - 1)]
        for mode in MODES:
            st = process(bytes(m), mode=mode)               # must not raise
            if mode in ("full", "full_fixed", "validated") and st.importable:
                assert not score_doc(fx.truth, st)["fin_error"], (kind, mode)


def test_odd_but_valid_pdfs_are_never_ready():
    def build(fn):
        d = pymupdf.open()
        fn(d)
        return d.tobytes()

    def letter(d):
        d.new_page().insert_text((72, 72), "Dear customer, this is a letter. " * 8)

    def dates_only(d):
        p = d.new_page()
        for i in range(30):
            p.insert_text((40, 60 + i * 12), f"{i % 28 + 1:02d}/01/2026 hello 1,000.00 2,000.00")

    def header_only(d):
        d.new_page().insert_text((40, 60), "Date Narration Debit Credit Balance")

    for fn in (lambda d: d.new_page(), letter, dates_only, header_only):
        for mode in ("validated", "full", "full_fixed"):
            assert not process(build(fn), mode=mode).importable


def test_too_many_pages_rejected():
    d = pymupdf.open()
    for _ in range(extract.MAX_PAGES + 1):
        d.new_page().insert_text((40, 40), "x")
    assert process(d.tobytes()).status == Status.UNSUPPORTED


# ----------------------------------------------------------------------------- exports
def test_csv_neutralises_spreadsheet_formulas():
    for evil in ("=HYPERLINK(\"http://x\",\"y\")", "+1+1", "-2+3", "@SUM(A1:A9)", chr(9) + "x"):
        assert csv_safe(evil).startswith("'")
    assert csv_safe("UPI/DR/1234") == "UPI/DR/1234"
    st = Statement(opening=Decimal(0), closing=Decimal(5), txns=[
        Txn(idx=0, page=1, date=date(2026, 1, 1), description="=cmd|' /C calc'!A0", credit=Decimal(5), balance=Decimal(5))])
    row = list(csv.reader(io.StringIO(to_csv(st))))[1]
    assert row[3].startswith("'=")


def test_aa_shape_keeps_zero_amounts():
    st = Statement(opening=Decimal(0), closing=Decimal(0), txns=[
        Txn(idx=0, page=1, date=date(2026, 1, 1), description="zero debit", debit=Decimal("0.00"), balance=Decimal(0))])
    assert to_aa_like(st)["transactions"][0]["amount"] == "0.00"


# ----------------------------------------------------------------------------- CLI
def test_cli_exit_codes(tmp_path, capsys):
    fx = make_fixture("A", 11, "clean")
    ok = tmp_path / "ok.pdf"
    ok.write_bytes(fx.pdf)
    assert cli.main([str(ok), "--quiet"]) == 0
    bad = make_fixture("A", 21, "src_missing_row")
    p = tmp_path / "bad.pdf"
    p.write_bytes(bad.pdf)
    assert cli.main([str(p), "--quiet", "--json", str(tmp_path / "o.json"), "--csv", str(tmp_path / "o.csv")]) == 2
    assert (tmp_path / "o.json").exists() and (tmp_path / "o.csv").exists()
    assert cli.main([str(tmp_path / "nope.pdf")]) == 1
    assert "cannot read" in capsys.readouterr().err
