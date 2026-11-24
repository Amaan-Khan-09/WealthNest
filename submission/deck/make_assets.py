"""Build deck assets from real pipeline output on the demo sample (nothing typed by hand)."""
import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from statement_guard.pipeline import process  # noqa: E402

pdf = (ROOT / "fixtures/samples/2_amount_mismatch_caught.pdf").read_bytes()
st = process(pdf, mode="full_fixed")
base = process(pdf, mode="baseline")
bad = min(f.row_idx for f in st.errors() if f.code == "balance_break")
t = st.txns[bad]
doc = pymupdf.open(stream=pdf, filetype="pdf")
page = doc[t.page - 1]
prev = st.txns[bad - 1].bbox
x0, y0, x1, y1 = t.bbox
r = pymupdf.Rect(30, max(0, min(y0, prev[1]) - 40), 565, y1 + 34)
sh = page.new_shape()
sh.draw_rect(pymupdf.Rect(x0 - 2, y0 - 1.5, x1 + 2, y1 + 1.5))
sh.finish(color=(0.89, 0.29, 0.28), width=1.6)
sh.commit()
page.get_pixmap(clip=r, dpi=170).save(ROOT / "docs/img/worked_example.png")
info = {
    "status": st.status.value, "baseline_status": base.status.value, "row": bad + 1, "rows": len(st.txns),
    "flags": [f.message for f in st.errors()], "baseline_closing": str(base.closing), "closing": str(st.closing),
    "row_debit": str(t.debit), "row_credit": str(t.credit), "row_balance": str(t.balance),
}
(ROOT / "results" / "worked_example.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
print(json.dumps(info, indent=1))
