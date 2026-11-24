"""Smoke test of the Streamlit demo's real entry point (no browser needed)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


def banner_text(at: AppTest) -> str:
    return " ".join(m.value for m in (list(at.success) + list(at.error) + list(at.warning)))


def test_landing_then_clean_then_error_sample():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Pick a sample" in i.value for i in at.info)
    labels = [b.label for b in at.sidebar.button]
    assert len(labels) == 5
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert "READY TO IMPORT" in banner_text(at)
    at.sidebar.button[1].click().run()          # amount mismatch sample
    assert not at.exception
    assert "NEEDS REVIEW" in banner_text(at)
    at.sidebar.button[4].click().run()          # image-only sample
    assert "UNSUPPORTED" in banner_text(at)


def test_reviewer_can_fix_the_mismatch_and_unlock_import():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.button[1].click().run()
    assert "NEEDS REVIEW" in banner_text(at)
    from statement_guard.pipeline import process
    st0 = process((Path(__file__).resolve().parent.parent / "fixtures/samples/2_amount_mismatch_caught.pdf").read_bytes())
    bad = min(f.row_idx for f in st0.errors() if f.code == "balance_break")
    t = st0.txns[bad]
    # apply the fix through the same review API the Re-validate button uses
    from statement_guard.review import apply_table_edits, table_rows
    rows = table_rows(st0)
    delta = t.balance - st0.txns[bad - 1].balance
    rows[bad]["debit" if delta < 0 else "credit"] = abs(delta)
    fixed = apply_table_edits(st0, rows)
    assert fixed.importable, [f.message for f in fixed.errors()]


def test_switching_pipeline_reprocesses_the_same_file():
    """The baseline (no checks) imports the defective sample; the guarded pipeline stops it."""
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.button[1].click().run()
    assert "NEEDS REVIEW" in banner_text(at)
    at.sidebar.selectbox[0].select("baseline").run()
    assert not at.exception
    assert "READY TO IMPORT" in banner_text(at)
    at.sidebar.selectbox[0].select("full_fixed").run()
    assert "NEEDS REVIEW" in banner_text(at)


def test_deep_link_opens_a_sample_directly():
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["sample"] = "3"
    at.run()
    assert not at.exception
    assert "NEEDS REVIEW" in banner_text(at)
