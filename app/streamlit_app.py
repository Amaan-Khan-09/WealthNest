"""Statement Guard demo.  Run:  streamlit run app/streamlit_app.py

Synthetic statements only. Uploaded files are held in memory for the session and never written to disk."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from decimal import Decimal  # noqa: E402

import pandas as pd  # noqa: E402
import pymupdf  # noqa: E402
import streamlit as st  # noqa: E402

from statement_guard.export import to_aa_like, to_csv, to_json  # noqa: E402
from statement_guard.models import Status  # noqa: E402
from statement_guard.pipeline import MODES, process  # noqa: E402
from statement_guard.review import apply_table_edits, table_rows  # noqa: E402

SAMPLES = ROOT / "fixtures" / "samples"
MAX_UPLOAD_MB = 10

st.set_page_config(page_title="Statement Guard", page_icon="🧾", layout="wide")

BANNER = {
    Status.READY: ("success", "READY TO IMPORT", "Every check passed. Nothing was auto-changed."),
    Status.READY_AUTOFIXED: ("warning", "READY TO IMPORT, with auto-corrections",
                             "Passed after evidence-backed repairs. Each repair is listed below; spot-check them."),
    Status.READY_REVIEWED: ("success", "READY TO IMPORT (human-reviewed)", "A reviewer edited this and it re-validated."),
    Status.NEEDS_REVIEW: ("error", "NEEDS REVIEW. Not import-ready", "At least one check failed. Nothing is imported until it is fixed."),
    Status.UNSUPPORTED: ("error", "UNSUPPORTED. Routed to review", "This file cannot be read reliably, so nothing was guessed."),
}


def load(name: str, data: bytes) -> None:
    st.session_state.pdf = data
    st.session_state.name = name
    st.session_state.stmt = process(data, mode=st.session_state.get("mode", "full_fixed"), name=name)
    st.session_state.original = st.session_state.stmt
    st.session_state.rev = st.session_state.get("rev", 0) + 1


def crop_png(pdf: bytes, page_no: int, bbox, prev_bbox=None) -> bytes:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        page = doc[page_no - 1]
        x0, y0, x1, y1 = bbox
        top = min(y0, prev_bbox[1]) if prev_bbox else y0
        r = pymupdf.Rect(0, max(0, top - 26), page.rect.width, min(page.rect.height, y1 + 26))
        sh = page.new_shape()
        sh.draw_rect(pymupdf.Rect(x0 - 2, y0 - 1.5, x1 + 2, y1 + 1.5))
        sh.finish(color=(0.85, 0.1, 0.1), width=1.3)
        sh.commit()
        return page.get_pixmap(clip=r, dpi=120).tobytes("png")
    finally:
        doc.close()


# ---------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Statement Guard")
    st.caption("Bank-statement PDF → checked transactions, or a precise reason it can't be trusted. "
               "**Synthetic data only. Do not upload real statements.**")
    st.selectbox("Pipeline", MODES, index=MODES.index("full_fixed"), key="mode",
                 help="full_fixed = the demo pipeline. baseline/naive show what happens without checks.")
    st.subheader("Try a sample")
    labels = {p.name: p for p in sorted(SAMPLES.glob("*.pdf"))}
    for fname, p in labels.items():
        if st.button(fname.replace(".pdf", "").replace("_", " ")[2:].capitalize(), key=f"s_{fname}", use_container_width=True):
            load(fname, p.read_bytes())
    st.subheader("Or upload")
    up = st.file_uploader("PDF (synthetic only)", type=["pdf"], label_visibility="collapsed")
    if up is not None and st.session_state.get("name") != up.name:
        if up.size > MAX_UPLOAD_MB * 1_000_000:
            st.error(f"File larger than {MAX_UPLOAD_MB} MB.")
        else:
            load(up.name, up.getvalue())

if st.session_state.get("pdf") and st.session_state.get("stmt_mode", st.session_state["mode"]) != st.session_state["mode"]:
    load(st.session_state.name, st.session_state.pdf)          # pipeline changed: re-run on the same file
st.session_state.stmt_mode = st.session_state["mode"]
_q = st.query_params.get("sample")
if _q and st.session_state.get("loaded_q") != _q:          # deep link: ?sample=2 opens the 2nd sample
    st.session_state.loaded_q = _q
    _hit = [p for n, p in labels.items() if n.startswith(f"{_q}_")]
    if _hit:
        load(_hit[0].name, _hit[0].read_bytes())
stmt = st.session_state.get("stmt")
st.title("Statement Guard")
if stmt is None:
    st.info("Pick a sample on the left. Start with **1 clean statement**, then **2 amount mismatch caught**.")
    st.stop()

# ---------------------------------------------------------------------------- result
kind, title, sub = BANNER[stmt.status]
getattr(st, kind)(f"**{title}**  \n{sub}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows extracted", len(stmt.txns))
c2.metric("Opening balance", f"{stmt.opening:,.2f}" if stmt.opening is not None else "not found")
c3.metric("Closing balance", f"{stmt.closing:,.2f}" if stmt.closing is not None else "not found")
c4.metric("Verification", {"full_chain": "row-by-row", "totals_only": "totals only", "none": "none"}[stmt.verification_level])

tab_res, tab_fix, tab_exp = st.tabs(["Why this status", "Review & fix", "Export"])

with tab_res:
    errs = stmt.errors()
    if errs:
        st.subheader(f"{len(errs)} check(s) failed")
        st.dataframe(pd.DataFrame([{"row": (f.row_idx + 1 if f.row_idx is not None else "whole statement"),
                                    "check": f.code, "why": f.message} for f in errs]),
                     hide_index=True, use_container_width=True)
    else:
        st.success("All checks passed: opening + credits − debits = closing, and every running balance follows from its row.")
    for f in stmt.flags:
        if f.severity == "info":
            st.caption(f"ℹ️ {f.message}")
    if stmt.repairs:
        st.subheader("Auto-corrections (each confirmed by the printed balances)")
        st.dataframe(pd.DataFrame([{"row": r.row_idx + 1 if r.row_idx is not None else "-", "kind": r.kind, "field": r.field,
                                    "printed": r.before, "corrected to": r.after, "evidence": r.evidence}
                                   for r in stmt.repairs]), hide_index=True, use_container_width=True)
    if stmt.reviewer_edits:
        st.subheader("Reviewer edits")
        st.write("\n".join(f"- {e}" for e in stmt.reviewer_edits))
    if stmt.layout_notes:
        st.caption("Layout notes: " + "; ".join(stmt.layout_notes))
    st.caption(f"Pipeline: {stmt.mode} · {stmt.runtime_ms:.0f} ms · {stmt.page_count} page(s)")

with tab_fix:
    if stmt.status == Status.UNSUPPORTED:
        st.warning("Nothing to edit: the file could not be read. Re-export a text-based PDF from the bank, "
                   "or enter the statement manually.")
    else:
        bad_rows = sorted({f.row_idx for f in stmt.errors() if f.row_idx is not None})
        if bad_rows:
            st.subheader("Suspected rows: evidence from the source PDF")
            pdf = st.session_state.get("pdf")
            for ri in bad_rows[:4]:
                t = stmt.txns[ri]
                with st.container(border=True):
                    why = "; ".join(f.message for f in stmt.errors() if f.row_idx == ri)
                    st.markdown(f"**Row {ri + 1}** · page {t.page} · extracted: "
                                f"{t.date} · debit {t.debit} · credit {t.credit} · balance {t.balance}")
                    st.text(why)                      # plain text: flag messages can echo PDF content
                    for f in stmt.errors():
                        imp = f.evidence.get("balances_imply") if f.row_idx == ri else None
                        if imp and imp["amount"] != "0":
                            st.info(f"Hint: the printed balances imply a {imp['direction']} of {Decimal(imp['amount']):,.2f} "
                                    "on this row. Confirm against the source before editing.")
                    if t.bbox and pdf:
                        prev = stmt.txns[ri - 1].bbox if ri > 0 and stmt.txns[ri - 1].page == t.page else None
                        st.image(crop_png(pdf, t.page, t.bbox, prev), caption="Red box = the extracted row")
            if len(bad_rows) > 4:
                st.caption(f"{len(bad_rows) - 4} more suspected rows in the table below.")
        elif stmt.errors():
            st.info("The failed checks are about the statement as a whole (see 'Why this status').")
        st.subheader("Edit extracted values, then re-validate")
        st.caption("Add, delete or change rows. Re-validation applies the same checks; "
                   "only a clean result unlocks import.")
        df = pd.DataFrame(table_rows(stmt))
        for col in ("debit", "credit", "balance"):
            df[col] = df[col].map(lambda v: None if v is None else str(v))
        edited = st.data_editor(
            df, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"ed_{st.session_state.get('rev', 0)}",
            column_config={"_orig": None, "page": st.column_config.NumberColumn(disabled=True),
                           "date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                           "debit": st.column_config.TextColumn(), "credit": st.column_config.TextColumn(),
                           "balance": st.column_config.TextColumn()})
        cc1, cc2 = st.columns(2)
        with cc1:
            op = st.text_input("Opening balance", value="" if stmt.opening is None else str(stmt.opening))
        with cc2:
            cl = st.text_input("Closing balance", value="" if stmt.closing is None else str(stmt.closing))
        if st.button("Re-validate", type="primary"):
            try:
                new = apply_table_edits(stmt, edited.to_dict("records"),
                                        opening=Decimal(op.replace(",", "")) if op.strip() else None,
                                        closing=Decimal(cl.replace(",", "")) if cl.strip() else None)
                st.session_state.stmt = new
                st.session_state.rev = st.session_state.get("rev", 0) + 1
                st.rerun()
            except (ValueError, ArithmeticError) as e:
                st.error(f"Could not apply edits: {e}")
        if st.session_state.get("original") is not stmt and st.button("Reset to extracted result"):
            st.session_state.stmt = st.session_state.original
            st.session_state.rev = st.session_state.get("rev", 0) + 1
            st.rerun()

with tab_exp:
    if stmt.importable:
        st.success("Import-ready export")
        st.download_button("Download JSON (import-ready)", to_json(stmt), file_name="statement.json", mime="application/json")
        st.download_button("Download CSV", to_csv(stmt), file_name="statement.csv", mime="text/csv")
        with st.expander("Illustrative canonical shape (modelled on the public AA deposit schema)"):
            st.json(to_aa_like(stmt))
    else:
        st.warning("Import export is disabled while the statement is unresolved.")
        st.download_button("Download diagnostics JSON (NOT import-ready)", to_json(stmt), file_name="diagnostics.json",
                           mime="application/json")
