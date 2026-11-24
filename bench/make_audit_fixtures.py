"""Build the known-answer synthetic files for the live-app audit (nothing here is a real statement).

    python -m bench.make_audit_fixtures      # writes fixtures/audit/

Files: a SHORT 3-row statement (the 'ordinary edge case': few transactions per column). The clean, defective
and image-only files for the audit already live in fixtures/samples/ (1, 2 and 5).
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "audit"


def short_statement() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    f = "helv"
    cols = {"date": 40, "narr": 110, "debit": 380, "credit": 450, "bal": 540}

    def right(x, y, txt, size=9):
        page.insert_text((x - pymupdf.get_text_length(txt, fontname=f, fontsize=size), y), txt, fontname=f, fontsize=size)

    page.insert_text((40, 40), "Sample Savings Bank (synthetic)", fontname="hebo", fontsize=12)
    page.insert_text((40, 54), "Statement of Account  |  Synthetic sample for testing. Not a real bank statement.", fontname=f, fontsize=7.5)
    page.insert_text((40, 72), "Opening Balance: 10,000.00", fontname=f, fontsize=9)
    y = 96
    for x, h in ((cols["date"], "Date"), (cols["narr"], "Narration")):
        page.insert_text((x, y), h, fontname="hebo", fontsize=9)
    right(cols["debit"], y, "Debit")
    right(cols["credit"], y, "Credit")
    right(cols["bal"], y, "Balance")
    rows = [("01/02/2026", "SALARY CREDIT (SYNTHETIC)", None, "5,000.00", "15,000.00"),
            ("02/02/2026", "UPI/DR/000000000001/SAMPLE STORE", "2,000.00", None, "13,000.00"),
            ("03/02/2026", "GROCERIES SAMPLE MART", "500.00", None, "12,500.00")]
    for d, n, dr, cr, b in rows:
        y += 14
        page.insert_text((cols["date"], y), d, fontname=f, fontsize=9)
        page.insert_text((cols["narr"], y), n, fontname=f, fontsize=9)
        if dr:
            right(cols["debit"], y, dr)
        if cr:
            right(cols["credit"], y, cr)
        right(cols["bal"], y, b)
    page.insert_text((40, y + 26), "Closing Balance: 12,500.00", fontname=f, fontsize=9)
    return doc.tobytes()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "short_statement_synthetic.pdf").write_bytes(short_statement())
    print("wrote", OUT / "short_statement_synthetic.pdf")
