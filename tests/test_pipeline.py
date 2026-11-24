"""End-to-end tests on actual synthetic PDFs (generated in memory, seeded)."""
import json
from decimal import Decimal

import pymupdf
import pytest

from bench.generator import make_fixture
from bench.metrics import score_doc
from statement_guard.export import to_aa_like, to_csv, to_json
from statement_guard.models import Status
from statement_guard.pipeline import process
from statement_guard.review import apply_table_edits, table_rows


def run(layout, seed, cat, mode="full"):
    fx = make_fixture(layout, seed, cat)
    return fx, process(fx.pdf, mode=mode, name=fx.name)


@pytest.mark.parametrize("layout", ["A", "B", "C", "D"])
def test_clean_statements_extract_exactly_and_are_ready(layout):
    fx, st = run(layout, 11, "clean")
    sc = score_doc(fx.truth, st)
    assert st.status == Status.READY, [f.message for f in st.errors()]
    assert not sc["fin_error"] and sc["missed"] == 0 and sc["extra"] == 0
    assert st.verification_level == "full_chain"


def test_generator_is_deterministic_and_truth_is_independent_of_parser():
    a = make_fixture("A", 5, "clean")
    b = make_fixture("A", 5, "clean")
    assert json.dumps(a.truth, sort_keys=True) == json.dumps(b.truth, sort_keys=True)
    rows = a.truth["printed_rows"]
    bal = Decimal(a.truth["opening"])
    for r in rows:                      # ledger arithmetic holds in the ground truth itself
        bal += Decimal(r["credit"] or 0) - Decimal(r["debit"] or 0)
        assert bal == Decimal(r["balance"])
    assert bal == Decimal(a.truth["closing"])


def test_missing_row_in_source_is_caught_before_import():
    fx, st = run("A", 21, "src_missing_row")
    assert st.status == Status.NEEDS_REVIEW and not st.importable
    assert any(f.code == "balance_break" for f in st.errors())
    # the baseline imports it silently
    assert process(fx.pdf, mode="baseline").importable


def test_amount_tamper_and_duplicate_are_not_auto_repaired_on_clean_text():
    for cat in ("src_amount_tamper", "src_dup_row"):
        fx, st = run("B", 22, cat)
        assert st.status == Status.NEEDS_REVIEW and not st.repairs, cat


def test_ocr_damage_repaired_only_with_balance_evidence_and_logged():
    fx, st = run("A", 1002, "ocr_noise")
    sc = score_doc(fx.truth, st)
    if st.status == Status.READY_AUTOFIXED:
        assert not sc["fin_error"]
        assert all(r.evidence for r in st.repairs)
    else:
        assert st.status == Status.NEEDS_REVIEW


def test_image_only_pdf_is_unsupported_not_guessed():
    fx, st = run("C", 3, "scan_only")
    assert st.status == Status.UNSUPPORTED and not st.txns and not st.importable


@pytest.mark.parametrize("blob", [b"", b"not a pdf", b"%PDF-1.4\ngarbage"])
def test_garbage_input_is_unsupported(blob):
    assert process(blob).status == Status.UNSUPPORTED


def test_encrypted_pdf_unsupported():
    fx = make_fixture("A", 4, "clean")
    d = pymupdf.open(stream=fx.pdf, filetype="pdf")
    enc = d.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    assert process(enc).status == Status.UNSUPPORTED


def test_oversized_input_rejected():
    assert process(b"%PDF" + b"0" * 16_000_000).status == Status.UNSUPPORTED


def test_watermark_and_blank_date_handled_by_robust_not_baseline():
    fx, st = run("D", 4001, "watermark")
    assert not score_doc(fx.truth, st)["any_error"]
    base = score_doc(fx.truth, process(fx.pdf, mode="baseline"))
    assert base["any_error"]


def test_reviewer_fix_reruns_validation_and_unlocks_import():
    fx, st = run("A", 21, "src_missing_row")
    assert not st.importable
    rows = table_rows(st)
    # reviewer inserts the row that the source statement dropped (taken from the original ledger)
    k = fx.truth["source_defect"]["row"]
    gone = fx.truth["source_defect"]["removed"]
    from datetime import date
    rows.insert(k, {"_orig": None, "date": date.fromisoformat(gone["date"]), "description": gone["description"],
                    "debit": gone["debit"], "credit": gone["credit"], "balance": gone["balance"]})
    fixed = apply_table_edits(st, rows)
    assert fixed.status == Status.READY_REVIEWED and fixed.reviewer_edits
    # an edit that does not fix the problem stays blocked
    bad = apply_table_edits(st, table_rows(st))
    assert bad.status == Status.NEEDS_REVIEW


def test_exports_are_exact_decimal_strings():
    fx, st = run("A", 11, "clean")
    js = json.loads(to_json(st))
    assert js["status"] == "READY"
    assert js["txns"][0]["debit"] is None or isinstance(js["txns"][0]["debit"], str)
    assert to_csv(st).splitlines()[0].startswith("row,page,date")
    aa = to_aa_like(st)
    assert aa["transactions"][0]["type"] in ("DEBIT", "CREDIT")


# ----------------------------------------------------------------------------- narration that looks like a label
def _mini_statement(narr_row2: str) -> bytes:
    """Hand-built 3-row statement; row 2's narration is attacker/bank controlled."""
    doc = pymupdf.open()
    page = doc.new_page()
    f = "helv"
    cols = {"date": 40, "narr": 110, "debit": 380, "credit": 450, "bal": 540}

    def right(x, y, txt):
        page.insert_text((x - pymupdf.get_text_length(txt, fontname=f, fontsize=9), y), txt, fontname=f, fontsize=9)

    y = 80
    page.insert_text((40, 60), "Opening Balance: 10,000.00", fontname=f, fontsize=9)
    for x, h in ((cols["date"], "Date"), (cols["narr"], "Narration")):
        page.insert_text((x, y), h, fontname=f, fontsize=9)
    right(cols["debit"], y, "Debit")
    right(cols["credit"], y, "Credit")
    right(cols["bal"], y, "Balance")
    rows = [("01/02/2026", "SALARY CREDIT", None, "5,000.00", "15,000.00"),
            ("02/02/2026", narr_row2, "2,000.00", None, "13,000.00"),
            ("03/02/2026", "GROCERIES", "500.00", None, "12,500.00")]
    for d, n, dr, cr, b in rows:
        y += 14
        page.insert_text((cols["date"], y), d, fontname=f, fontsize=9)
        page.insert_text((cols["narr"], y), n, fontname=f, fontsize=9)
        if dr:
            right(cols["debit"], y, dr)
        if cr:
            right(cols["credit"], y, cr)
        right(cols["bal"], y, b)
    page.insert_text((40, y + 24), "Closing Balance: 12,500.00", fontname=f, fontsize=9)
    return doc.tobytes()


def test_transaction_with_label_like_narration_is_kept_by_the_fixed_pipeline():
    pdf = _mini_statement("ACCOUNT CLOSING BALANCE TRANSFER")
    ok = process(pdf, mode="full_fixed")
    assert len(ok.txns) == 3 and ok.status == Status.READY, [f.message for f in ok.errors()]
    assert ok.closing == Decimal("12500.00")


def test_short_statement_with_one_or_two_entries_per_column_is_read_by_the_fixed_pipeline():
    st = process(_mini_statement("TRANSFER OUT"), mode="full_fixed")
    assert st.status == Status.READY and len(st.txns) == 3
    assert [(t.debit, t.credit) for t in st.txns] == [(None, Decimal("5000.00")), (Decimal("2000.00"), None),
                                                      (Decimal("500.00"), None)]


def test_locked_pipeline_may_not_read_short_statements_but_never_imports_them_wrong():
    for narr in ("TRANSFER OUT", "ACCOUNT CLOSING BALANCE TRANSFER"):
        st = process(_mini_statement(narr), mode="full")
        assert not st.importable or [(t.debit, t.credit) for t in st.txns] == [
            (None, Decimal("5000.00")), (Decimal("2000.00"), None), (Decimal("500.00"), None)]


def test_balance_break_flag_carries_the_amount_the_balances_imply():
    fx, st = run("A", 1011, "src_amount_tamper")
    f = next(f for f in st.errors() if f.code == "balance_break")
    imp = f.evidence["balances_imply"]
    assert imp["direction"] in ("debit", "credit") and Decimal(imp["amount"]) > 0


def test_audit_short_statement_fixture_is_a_known_answer():
    """fixtures/audit/short_statement_synthetic.pdf is handed to the live-app audit; its result must stay known."""
    from bench.make_audit_fixtures import short_statement
    st = process(short_statement(), mode="full_fixed")
    assert st.status == Status.READY and len(st.txns) == 3
    assert st.opening == Decimal("10000.00") and st.closing == Decimal("12500.00")
    assert not process(short_statement(), mode="full").importable or len(process(short_statement(), mode="full").txns) == 3
