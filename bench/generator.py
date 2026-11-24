"""Seeded synthetic bank-statement generator with independently defined ground truth.

The ledger (opening balance, transactions, running balances) is built with exact Decimal
arithmetic *before* any rendering, using reportlab. The parser under test (PyMuPDF based) never sees
this code path, so ground truth is independent of the extraction logic.

Everything is fictional: bank names, merchants and amounts are invented. Not real statements.
"""
from __future__ import annotations

import io
import json
import random
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from statement_guard.money import fmt_indian  # noqa: E402  (formatting only; not parsing)

D = Decimal
CENT = D("0.01")


# ----------------------------------------------------------------------------- layouts
@dataclass
class Col:
    role: str          # date value_date narration ref debit credit amount indicator balance
    header: str
    w: float
    align: str = "l"   # alignment of cell values: l | r
    halign: str = "l"  # header alignment: l | r | c


@dataclass
class Layout:
    id: str
    split: str                      # dev | holdout
    bank: str
    cols: list[Col]
    date_fmt: str
    amount_mode: str = "split"      # split | suffix | indicator
    indicator_words: tuple[str, str] = ("DR", "CR")
    bal_style: str = "plain"        # plain | cr_suffix
    summary: str = "inline"         # inline | table_box | opening_row | none
    totals_printed: bool = False
    font: str = "Helvetica"
    size: float = 8.0
    carry_forward: bool = False
    blank_repeat_date: bool = False
    repeat_header: bool = True
    left: float = 36.0

    @property
    def has_balance(self) -> bool:
        return any(c.role == "balance" for c in self.cols)


def _L(*a, **k):
    return Layout(*a, **k)


LAYOUTS: dict[str, Layout] = {}


def _reg(l: Layout) -> None:
    LAYOUTS[l.id] = l


# ---- development layouts (parser is built and tuned against these) ----
_reg(_L("A", "dev", "Northbridge Bank (synthetic)", [
    Col("date", "Date", 56), Col("narration", "Narration", 170), Col("ref", "Chq./Ref.No.", 78),
    Col("debit", "Withdrawal Amt.", 70, "r"), Col("credit", "Deposit Amt.", 70, "r"),
    Col("balance", "Closing Balance", 78, "r")],
    "%d/%m/%y", summary="inline"))
_reg(_L("B", "dev", "Kaveri Co-op Bank (synthetic)", [
    Col("date", "Txn Date", 58), Col("value_date", "Value Date", 58), Col("narration", "Description", 160),
    Col("debit", "Debit", 72, "r", "r"), Col("credit", "Credit", 72, "r", "r"),
    Col("balance", "Balance", 82, "r", "r")],
    "%d-%b-%Y", summary="table_box", carry_forward=True, totals_printed=True))
_reg(_L("C", "dev", "Meridian Savings (synthetic)", [
    Col("date", "Date", 62), Col("narration", "Particulars", 210),
    Col("amount", "Amount", 100, "r", "r"), Col("balance", "Balance", 110, "r", "r")],
    "%d/%m/%Y", amount_mode="suffix", bal_style="cr_suffix", summary="opening_row"))
_reg(_L("D", "dev", "Lakeview Bank (synthetic)", [
    Col("date", "Date", 60), Col("narration", "Narration", 190), Col("ref", "Ref No", 64),
    Col("indicator", "Dr/Cr", 34, "l"), Col("amount", "Amount", 80, "r", "r"),
    Col("balance", "Balance", 88, "r", "r")],
    "%d/%m/%Y", amount_mode="indicator", summary="inline", blank_repeat_date=True))

# ---- holdout layouts (never used while developing the parser) ----
_reg(_L("E", "holdout", "Harbour Trust Bank (synthetic)", [
    Col("date", "Date", 66), Col("narration", "Details", 172),
    Col("debit", "Debit", 92, "r", "l"), Col("credit", "Credit", 92, "r", "l"),
    Col("balance", "Balance", 96, "r", "l")],
    "%d %b %Y", summary="table_box", totals_printed=True, size=8.5))
_reg(_L("F", "holdout", "Orchid Digital Bank (synthetic)", [
    Col("date", "Date", 58), Col("narration", "Transaction details", 200),
    Col("indicator", "Type", 44, "l", "c"), Col("amount", "Amount (INR)", 92, "r", "c"),
    Col("balance", "Running balance", 110, "r", "c")],
    "%d/%m/%Y", amount_mode="indicator", indicator_words=("Debit", "Credit"),
    summary="opening_row", carry_forward=True, size=8.0))
_reg(_L("G", "holdout", "Peakview Payments Bank (synthetic)", [
    Col("date", "Date", 62), Col("narration", "Description", 270),
    Col("debit", "Outflow", 94, "r", "r"), Col("credit", "Inflow", 94, "r", "r")],
    "%d.%m.%Y", summary="table_box", totals_printed=True))
_reg(_L("H", "holdout", "Sandalwood Gramin Bank (synthetic)", [
    Col("date", "Date", 58), Col("narration", "Narration", 180), Col("ref", "Ref", 66),
    Col("debit", "Withdrawal", 70, "r", "r"), Col("credit", "Deposit", 70, "r", "r"),
    Col("balance", "Balance", 80, "r", "r")],
    "%Y-%m-%d", summary="none", blank_repeat_date=True))

# ----------------------------------------------------------------------------- ledger
_MERCH = ["QuickBites", "FreshMart", "MetroRail Card", "StreamBox", "PetroPoint", "GreenLeaf Pharmacy",
          "CityCab", "BookNest", "UrbanStyle", "AquaPure Water", "SpiceRoute Foods", "TechHub Electronics"]
_PEOPLE = ["RAHUL SHARMA", "PRIYA NAIR", "S VENKATESH", "AMINA KHATUN", "JOSEPH D SOUZA", "K LAKSHMI DEVI",
           "MOHD IRFAN", "GURPREET SINGH"]
_COMPANIES = ["ACME PAYROLL SERVICES", "BRIGHTPATH LABS PVT LTD", "ORCHARD HOUSING SOCIETY", "NORTHSTAR INSURANCE"]


@dataclass
class Row:
    date: date
    desc: str
    ref: str
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal

    def to_json(self) -> dict:
        return {"date": self.date.isoformat(), "description": self.desc, "ref": self.ref,
                "debit": str(self.debit) if self.debit is not None else None,
                "credit": str(self.credit) if self.credit is not None else None,
                "balance": str(self.balance)}


def _money(rng: random.Random, lo: float, hi: float) -> Decimal:
    return D(str(round(rng.uniform(lo, hi), 2))).quantize(CENT)


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def _debit_desc(rng: random.Random) -> tuple[str, Decimal, str]:
    k = rng.random()
    if k < 0.45:
        m = rng.choice(_MERCH)
        return f"UPI/DR/{_digits(rng, 12)}/{m.upper()}/okpay/UPI PAYMENT REF", _money(rng, 40, 6000), _digits(rng, 12)
    if k < 0.60:
        return f"ATM WDL/{rng.choice(['DELHI', 'PUNE', 'KOCHI', 'HYDERABAD'])}/{_digits(rng, 6)}", D(rng.choice([2000, 5000, 10000, 20000])), _digits(rng, 6)
    if k < 0.72:
        return f"POS {_digits(rng, 4)}XXXXXX{_digits(rng, 4)} {rng.choice(_MERCH).upper()}", _money(rng, 200, 15000), _digits(rng, 8)
    if k < 0.84:
        return f"NEFT-N{_digits(rng, 9)}-{rng.choice(_COMPANIES)}-RENT/EMI SETTLEMENT", _money(rng, 8000, 60000), _digits(rng, 10)
    if k < 0.93:
        return f"IMPS/P2A/{_digits(rng, 12)}/{rng.choice(_PEOPLE)}", _money(rng, 500, 25000), _digits(rng, 12)
    return f"ACH D- {rng.choice(_COMPANIES)}-{_digits(rng, 8)}", _money(rng, 1500, 30000), _digits(rng, 8)


def _credit_desc(rng: random.Random) -> tuple[str, Decimal, str]:
    k = rng.random()
    if k < 0.30:
        return f"NEFT-N{_digits(rng, 9)}-{rng.choice(_COMPANIES)}-SALARY", _money(rng, 25000, 250000), _digits(rng, 10)
    if k < 0.75:
        return f"UPI/CR/{_digits(rng, 12)}/{rng.choice(_PEOPLE)}/okpay/UPI", _money(rng, 100, 30000), _digits(rng, 12)
    if k < 0.90:
        return f"IMPS/P2A/{_digits(rng, 12)}/{rng.choice(_PEOPLE)}", _money(rng, 500, 40000), _digits(rng, 12)
    return f"INT.PD {_digits(rng, 2)}-{_digits(rng, 2)}-2026 QTR CREDIT", _money(rng, 20, 900), _digits(rng, 6)


def build_ledger(rng: random.Random, n_rows: int, wide: bool, overdraft: bool) -> tuple[Decimal, list[Row]]:
    opening = _money(rng, 15000, 60000 if overdraft else 1500000)
    if wide:
        opening = _money(rng, 900000, 9000000)
    bal = opening
    d = date(2025, 4, 1) + timedelta(days=rng.randint(0, 400))
    rows: list[Row] = []
    for _ in range(n_rows):
        d += timedelta(days=rng.choice([0, 0, 1, 1, 2, 3]))
        want_credit = rng.random() < 0.34 or bal < D(1000)
        if want_credit:
            desc, amt, ref = _credit_desc(rng)
            if wide and rng.random() < 0.6:
                amt = _money(rng, 400000, 4500000)
            bal += amt
            rows.append(Row(d, desc, ref, None, amt, bal))
        else:
            desc, amt, ref = _debit_desc(rng)
            if wide and rng.random() < 0.5:
                amt = _money(rng, 100000, 1500000)
            if not overdraft:
                amt = min(amt, (bal * D("0.6")).quantize(CENT))
                if amt < D("10"):
                    desc, amt, ref = _credit_desc(rng)
                    bal += amt
                    rows.append(Row(d, desc, ref, None, amt, bal))
                    continue
            bal -= amt
            rows.append(Row(d, desc, ref, amt, None, bal))
    if overdraft and not any(r.balance < 0 for r in rows):
        # force at least one overdrawn balance by making one debit larger than the balance
        i = rng.randint(1, max(1, len(rows) - 2))
        extra = rows[i - 1].balance + _money(rng, 500, 4000)
        rows[i].debit = (rows[i].debit or D(0)) + extra if rows[i].debit else extra
        rows[i].credit = None
        # recompute balances from i onward
        b = rows[i - 1].balance
        for r in rows[i:]:
            b = b + (r.credit or D(0)) - (r.debit or D(0))
            r.balance = b
    return opening, rows


# ----------------------------------------------------------------------------- faults
CATEGORIES = [  # (name, weight)
    ("clean", 0.30), ("watermark", 0.10), ("blank_date", 0.08), ("wide_amounts", 0.10), ("overdraft", 0.06),
    ("ocr_noise", 0.14), ("src_missing_row", 0.07), ("src_dup_row", 0.04), ("src_amount_tamper", 0.05),
    ("scan_only", 0.06),
]


def pick_category(rng: random.Random) -> str:
    r, acc = rng.random(), 0.0
    for name, w in CATEGORIES:
        acc += w
        if r < acc:
            return name
    return "clean"


# ----------------------------------------------------------------------------- rendering
_CONF = {"0": "O", "1": "l", "5": "S", "8": "B", "2": "Z"}


def _noisy(rng: random.Random, s: str, p: float) -> str:
    """OCR-like corruption of a numeric string (the text layer of a poorly OCR'd scan)."""
    if rng.random() >= p or len(s) < 3:
        return s
    r = rng.random()
    idx = [i for i, c in enumerate(s) if c.isdigit()]
    if not idx:
        return s
    if r < 0.55:  # confusable letter
        cands = [i for i in idx if s[i] in _CONF]
        if cands:
            i = rng.choice(cands)
            return s[:i] + _CONF[s[i]] + s[i + 1:]
    if r < 0.85:  # dropped digit (integer part only)
        ip = [i for i in idx if i < s.find(".")] if "." in s else idx
        if len(ip) > 1:
            i = rng.choice(ip)
            return s[:i] + s[i + 1:]
    if "." in s:  # decimal point read as comma
        return s.replace(".", ",")
    return s


def _wrap(text: str, width: float, font: str, size: float) -> list[str]:
    out: list[str] = []
    cur = ""
    for word in text.split(" "):
        while stringWidth(word, font, size) > width:  # hard-break very long tokens
            k = len(word)
            while k > 1 and stringWidth(word[:k], font, size) > width:
                k -= 1
            if cur:
                out.append(cur)
                cur = ""
            out.append(word[:k])
            word = word[k:]
        trial = word if not cur else cur + " " + word
        if stringWidth(trial, font, size) <= width:
            cur = trial
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out or [""]


def _bal_text(layout: Layout, v: Decimal) -> str:
    if layout.bal_style == "cr_suffix":
        return f"{fmt_indian(abs(v))} {'Dr' if v < 0 else 'Cr'}"
    return fmt_indian(v)


def render_pdf(layout: Layout, opening: Decimal, closing: Decimal, rows: list[Row], total_d: Decimal,
               total_c: Decimal, category: str, seed: int) -> bytes:
    pages_total = _render(layout, opening, closing, rows, total_d, total_c, category, seed, 99)[1]
    return _render(layout, opening, closing, rows, total_d, total_c, category, seed, pages_total)[0]


def _render(layout, opening, closing, rows, total_d, total_c, category, seed, n_pages):
    rng = random.Random(seed * 7919 + 13)
    noise_p = 0.07 if category == "ocr_noise" else 0.0
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    f, fb, sz = layout.font, layout.font + "-Bold", layout.size
    lh = sz + 3.2
    page_no = 1
    left = layout.left
    xs, x = {}, left
    for col in layout.cols:
        xs[col.role] = x
        x += col.w
    cols = {col.role: col for col in layout.cols}
    table_right = x

    def num_text(s: str) -> str:
        return _noisy(rng, s, noise_p)

    def put(role: str, y: float, text: str, bold=False) -> None:
        col = cols.get(role)
        if col is None or not text:
            return
        c.setFont(fb if bold else f, sz)
        if col.align == "r":
            c.drawRightString(xs[role] + col.w - 3, y, text)
        else:
            c.drawString(xs[role] + 3, y, text)

    def furniture() -> float:
        c.setFont(fb, 11)
        c.drawString(left, H - 40, layout.bank)
        c.setFont(f, 7.5)
        c.drawString(left, H - 52, "Statement of Account  |  Branch: 0042 Example Road, Sample City")
        c.drawRightString(table_right, H - 40, f"Page {page_no} of {n_pages}")
        c.drawString(left, 30, "Synthetic sample generated for benchmarking. Not a real bank statement.")
        c.drawRightString(table_right, 30, f"Page {page_no} of {n_pages}")
        if category == "watermark":
            c.saveState()
            c.setFillGray(0.82)
            c.setFont("Helvetica-Bold", 54)
            c.translate(W / 2, H / 2)
            c.rotate(40)
            c.drawCentredString(0, 0, "CUSTOMER COPY")
            c.restoreState()
            c.setFillGray(0)
        return H - 72

    def table_header(y: float) -> float:
        c.setFont(fb, sz)
        for col in layout.cols:
            x0 = xs[col.role]
            if col.halign == "r":
                c.drawRightString(x0 + col.w - 3, y, col.header)
            elif col.halign == "c":
                c.drawCentredString(x0 + col.w / 2, y, col.header)
            else:
                c.drawString(x0 + 3, y, col.header)
        c.line(left, y - 3, table_right, y - 3)
        return y - lh - 3

    y = furniture()
    # ---- summary block
    d0 = rows[0].date if rows else date(2026, 1, 1)
    d1 = rows[-1].date if rows else date(2026, 1, 31)
    c.setFont(f, 8)
    c.drawString(left, y, f"Statement period: {d0.strftime('%d/%m/%Y')} to {d1.strftime('%d/%m/%Y')}   Account: XXXXXX{4321}   Currency: INR")
    y -= 16
    if layout.summary == "inline":
        c.setFont(fb, 8.5)
        c.drawString(left, y, f"Opening Balance: {fmt_indian(opening)}")
        if layout.totals_printed:
            c.drawString(left + 180, y, f"Total Debits: {fmt_indian(total_d)}")
            c.drawString(left + 340, y, f"Total Credits: {fmt_indian(total_c)}")
        y -= 16
    elif layout.summary == "table_box":
        labels = ["Opening Balance", "Total Debits", "Total Credits", "Closing Balance"]
        vals = [opening, total_d, total_c, closing]
        step = (table_right - left) / 4
        c.setFont(fb, 8)
        for i, lab in enumerate(labels):
            c.drawString(left + i * step + 2, y, lab)
        y -= lh + 1
        c.setFont(f, 8)
        for i, v in enumerate(vals):
            c.drawString(left + i * step + 2, y, fmt_indian(v))
        y -= 18
    y = table_header(y)
    body_bottom = 52.0

    def cf_row(label: str, bal: Decimal, y: float) -> float:
        c.setFont(fb, sz)
        put("narration", y, label, bold=True)
        put("balance", y, num_text(_bal_text(layout, bal)), bold=True)
        return y - lh

    def next_page() -> float:
        nonlocal page_no
        c.showPage()
        page_no += 1
        yy = furniture()
        return table_header(yy - 6) if layout.repeat_header else yy - 6

    if layout.summary == "opening_row":
        c.setFont(f, sz)
        put("date", y, d0.strftime(layout.date_fmt))
        put("narration", y, "OPENING BALANCE")
        put("balance", y, _bal_text(layout, opening))
        y -= lh

    prev_date = None
    prev_bal = opening
    for i, r in enumerate(rows):
        narr_col = cols["narration"]
        lines = _wrap(r.desc, narr_col.w - 6, f, sz)
        need = lh * len(lines) + (lh * 1.2 if layout.carry_forward else 0)
        if y - need < body_bottom:
            if layout.carry_forward:
                y = cf_row("CARRIED FORWARD", prev_bal, y)
            y = next_page()
            if layout.carry_forward:
                y = cf_row("BROUGHT FORWARD", prev_bal, y)
        c.setFont(f, sz)
        show_date = not (layout.blank_repeat_date and prev_date == r.date)
        if show_date:
            put("date", y, r.date.strftime(layout.date_fmt))
        if "value_date" in cols:
            put("value_date", y, (r.date + timedelta(days=0)).strftime(layout.date_fmt))
        put("narration", y, lines[0])
        if "ref" in cols:
            put("ref", y, r.ref)
        amt = r.debit if r.debit is not None else r.credit
        is_dr = r.debit is not None
        if layout.amount_mode == "split":
            if r.debit is not None:
                put("debit", y, num_text(fmt_indian(r.debit)))
            if r.credit is not None:
                put("credit", y, num_text(fmt_indian(r.credit)))
        elif layout.amount_mode == "suffix":
            put("amount", y, num_text(fmt_indian(amt)) + (" Dr" if is_dr else " Cr"))
        else:
            put("indicator", y, layout.indicator_words[0] if is_dr else layout.indicator_words[1])
            put("amount", y, num_text(fmt_indian(amt)))
        if layout.has_balance:
            put("balance", y, num_text(_bal_text(layout, r.balance)))
        for extra in lines[1:]:
            y -= lh
            put("narration", y, extra)
        y -= lh
        prev_date, prev_bal = r.date, r.balance

    # ---- closing
    y -= 4
    if layout.summary == "inline":
        c.setFont(fb, 8.5)
        c.drawString(left, y, f"Closing Balance: {fmt_indian(closing)}")
        y -= 14
    elif layout.summary == "opening_row":
        c.setFont(fb, sz)
        put("narration", y, "CLOSING BALANCE", bold=True)
        put("balance", y, _bal_text(layout, closing), bold=True)
        y -= 14
    c.setFont(f, 7)
    c.drawString(left, max(y - 8, 44), "*** End of statement ***  This is a computer generated statement.")
    c.showPage()
    c.save()
    return buf.getvalue(), page_no


def rasterize(pdf_bytes: bytes, dpi: int = 110) -> bytes:
    import pymupdf
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = pymupdf.open()
    for pg in src:
        pix = pg.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        newp = out.new_page(width=pg.rect.width, height=pg.rect.height)
        newp.insert_image(newp.rect, stream=pix.tobytes("png"))
    return out.tobytes()


# ----------------------------------------------------------------------------- one fixture
@dataclass
class Fixture:
    name: str
    split: str
    layout: str
    category: str
    seed: int
    pdf: bytes
    truth: dict = field(default_factory=dict)


def make_fixture(layout_id: str, seed: int, category: str | None = None) -> Fixture:
    layout = LAYOUTS[layout_id]
    rng = random.Random(seed)
    cat = category or pick_category(rng)
    if cat == "blank_date":
        layout = replace(layout, blank_repeat_date=True)
    n_rows = rng.randint(18, 64)
    opening, ledger = build_ledger(rng, n_rows, wide=(cat == "wide_amounts"), overdraft=(cat == "overdraft"))
    closing = ledger[-1].balance
    total_d = sum((r.debit or D(0) for r in ledger), D(0))
    total_c = sum((r.credit or D(0) for r in ledger), D(0))

    printed = [Row(r.date, r.desc, r.ref, r.debit, r.credit, r.balance) for r in ledger]
    defect = None
    if cat == "src_missing_row":
        k = rng.randint(2, len(printed) - 3)
        defect = {"type": "missing_row", "row": k, "removed": printed[k].to_json()}
        del printed[k]
    elif cat == "src_dup_row":
        k = rng.randint(2, len(printed) - 3)
        defect = {"type": "duplicate_row", "row": k}
        printed.insert(k + 1, Row(*(printed[k].date, printed[k].desc, printed[k].ref, printed[k].debit,
                                    printed[k].credit, printed[k].balance)))
    elif cat == "src_amount_tamper":
        k = rng.randint(2, len(printed) - 3)
        r = printed[k]
        old = (r.debit if r.debit is not None else r.credit)
        new = (old + D(rng.choice([10, 100, 1000, 250])) * rng.choice([1, -1])).quantize(CENT)
        if new <= 0:
            new = old + D(100)
        if r.debit is not None:
            r.debit = new
        else:
            r.credit = new
        defect = {"type": "amount_tamper", "row": k, "old": str(old), "new": str(new)}

    # a layout without running balance cannot print balances
    pdf = render_pdf(layout, opening, closing, printed, total_d, total_c, cat, seed)
    if cat == "scan_only":
        pdf = rasterize(pdf)

    # printed ground truth = what the page shows (balances only if the layout prints them)
    truth = {
        "layout": layout_id, "category": cat, "seed": seed, "split": layout.split,
        "opening": str(opening), "closing": str(closing),
        "has_balance": layout.has_balance,
        "printed_rows": [{**r.to_json(), "balance": str(r.balance) if layout.has_balance else None} for r in printed],
        "original_rows": [r.to_json() for r in ledger],
        "source_defect": defect,
        "image_only": cat == "scan_only",
        "expected_review": bool(defect) or cat == "scan_only",
        "summary_style": layout.summary,
    }
    # layouts that print neither opening nor closing give the parser nothing to anchor on
    truth["summary_printed"] = layout.summary != "none"
    name = f"{layout_id}_{cat}_{seed}"
    return Fixture(name, layout.split, layout_id, cat, seed, pdf, truth)


def write_fixture(fx: Fixture, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{fx.name}.pdf").write_bytes(fx.pdf)
    (out_dir / f"{fx.name}.truth.json").write_text(json.dumps(fx.truth, indent=1), encoding="utf-8")
