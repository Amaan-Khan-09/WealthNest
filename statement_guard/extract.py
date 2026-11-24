"""PDF -> raw statement extraction (text-layer PDFs only).

Two extractors share the same low-level primitives:

* ``extract_baseline``  - the straightforward parser we benchmark against: find the header row, split columns
  at midpoints between header centres, a row starts where the date cell parses, other lines are wrapped
  narration. Our own reproduction; it makes no claim about how any production importer behaves.
* ``extract_robust``    - data-driven numeric columns (clustered on the right/left edge of the numbers),
  page-furniture and watermark filtering, blank-date rows, carry-forward checkpoints, label-above-value
  summary boxes and a header-free structural fallback.

PDFs are untrusted input: size/page/word caps apply and nothing is executed or rendered here.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pymupdf

from .models import Statement, Txn
from .money import Amount, parse_amount, parse_date

MAX_BYTES = 15_000_000
MAX_PAGES = 40
MAX_WORDS_PER_PAGE = 30_000


class UnsupportedPDF(Exception):
    pass


# ----------------------------------------------------------------------------- primitives
@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    page: int

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class Line:
    page: int
    y: float
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (min(w.x0 for w in self.words), min(w.y0 for w in self.words),
                max(w.x1 for w in self.words), max(w.y1 for w in self.words))


def open_pdf(src: bytes | str | Path) -> pymupdf.Document:
    data = src if isinstance(src, (bytes, bytearray)) else Path(src).read_bytes()
    if len(data) > MAX_BYTES:
        raise UnsupportedPDF(f"file larger than {MAX_BYTES // 1_000_000} MB")
    try:
        doc = pymupdf.open(stream=bytes(data), filetype="pdf")
    except Exception as e:  # corrupt / not a PDF
        raise UnsupportedPDF(f"cannot open as PDF: {type(e).__name__}") from e
    if doc.needs_pass or doc.is_encrypted:
        raise UnsupportedPDF("encrypted PDF")
    if len(doc) == 0 or len(doc) > MAX_PAGES:
        raise UnsupportedPDF(f"page count {len(doc)} outside 1..{MAX_PAGES}")
    return doc


def read_words(doc: pymupdf.Document, drop_oversized: bool) -> tuple[list[list[Word]], int]:
    """Return per-page word lists and the number of dropped (watermark-like) words."""
    pages: list[list[Word]] = []
    dropped = 0
    for pno, page in enumerate(doc, start=1):
        raw = page.get_text("words")
        if len(raw) > MAX_WORDS_PER_PAGE:
            raise UnsupportedPDF("too many words on one page")
        ws = [Word(r[0], r[1], r[2], r[3], r[4], pno) for r in raw if r[4].strip()]
        if drop_oversized and ws:
            med = statistics.median(w.h for w in ws)
            keep = [w for w in ws if w.h <= 2.2 * med]
            dropped += len(ws) - len(keep)
            ws = keep
        pages.append(ws)
    return pages, dropped


def group_lines(words: list[Word]) -> list[Line]:
    if not words:
        return []
    med = statistics.median(w.h for w in words)
    tol = max(2.0, 0.45 * med)
    ws = sorted(words, key=lambda w: (w.yc, w.x0))
    lines: list[list[Word]] = []
    ys: list[float] = []
    for w in ws:
        if lines and abs(w.yc - ys[-1]) <= tol:
            lines[-1].append(w)
            ys[-1] = sum(x.yc for x in lines[-1]) / len(lines[-1])
        else:
            lines.append([w])
            ys.append(w.yc)
    return [Line(ws_[0].page, y, sorted(ws_, key=lambda w: w.x0)) for ws_, y in zip(lines, ys)]


def is_image_only(doc: pymupdf.Document) -> bool:
    chars = sum(len(p.get_text("text").strip()) for p in doc)
    return chars < 60 * len(doc)


# ----------------------------------------------------------------------------- header handling
ROLE_PATTERNS = [
    ("value_date", r"value\s*(date|dt)"),
    ("date", r"^(txn\.?\s*|transaction\s*|post(ing)?\s*)?(date|dt)$"),
    ("narration", r"narration|description|particulars|details|remarks"),
    ("ref", r"chq|cheque|\bref|utr|instrument"),
    ("indicator", r"^(dr\s*/\s*cr|cr\s*/\s*dr|d\s*/\s*c|type)$"),
    ("debit", r"withdraw|debit|^dr\.?$|paid out"),
    ("credit", r"deposit|credit|^cr\.?$|paid in"),
    ("amount", r"^amount"),
    ("balance", r"balance|^bal\.?$"),
]
NUMERIC_ROLES = ("debit", "credit", "amount", "balance")


def classify_header(text: str) -> str | None:
    t = text.strip().lower()
    for role, pat in ROLE_PATTERNS:
        if re.search(pat, t):
            return role
    return None


@dataclass
class HCell:
    role: str | None
    text: str
    x0: float
    x1: float

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


def header_cells(line: Line, gap: float = 5.5) -> list[HCell]:
    cells: list[HCell] = []
    for w in line.words:
        if cells and w.x0 - cells[-1].x1 < gap:
            c = cells[-1]
            c.text += " " + w.text
            c.x1 = w.x1
        else:
            cells.append(HCell(None, w.text, w.x0, w.x1))
    for c in cells:
        c.role = classify_header(c.text)
    return cells


def find_header(lines: list[Line]) -> tuple[int, list[HCell]] | None:
    for i, ln in enumerate(lines):
        cells = header_cells(ln)
        roles = [c.role for c in cells if c.role]
        if len(set(roles)) >= 3 and "date" in roles and "narration" in roles and any(r in NUMERIC_ROLES for r in roles):
            return i, [c for c in cells if c.role]
    return None


# ----------------------------------------------------------------------------- numeric helpers
def _has_decimals(a: Amount) -> bool:
    return "." in a.text or a.suffix is not None


def balance_value(a: Amount) -> Decimal:
    """Running balances: 'Dr' suffix, '(..)' or '-' mean overdrawn."""
    return -a.value if (a.negative or a.suffix == "Dr") else a.value


def looks_numericish(text: str) -> bool:
    core = [c for c in text if c.isalnum() or c in ".,"]
    if not core or not any(c.isdigit() for c in core) and not any(c in "OlISBZ" for c in core):
        return False
    if re.search(r"[/\-]", text) and not re.match(r"^[-(]?[\dOlISBZ,.]+\)?$", text):
        return False  # dates, refs
    allowed = set("0123456789.,OolISBZ|") | set("DrCr")
    return sum(c in allowed for c in text) / len(text) >= 0.8 and any(c.isdigit() for c in text)


DR_WORDS = {"dr", "debit", "d", "dr."}
CR_WORDS = {"cr", "credit", "c", "cr."}

FURNITURE = re.compile(r"page\s*\d+\s*(of|/)\s*\d+|synthetic sample|computer generated|end of statement|"
                       r"statement of account|\*\*\*|continued on|statement period")
FWD = re.compile(r"(carried|brought)\s+forward|\bc/?f\b|\bb/?f\b")
OPENING = re.compile(r"opening\s+balance")
CLOSING = re.compile(r"closing\s+balance")


# ----------------------------------------------------------------------------- summary block
_LABELS = {
    "opening": ["opening", "balance"],
    "closing": ["closing", "balance"],
    "total_debits": ["total", "debits"],
    "total_credits": ["total", "credits"],
}
_LABEL_ALIASES = {"total_debits": [["total", "debits"], ["total", "withdrawals"], ["total", "debit"]],
                  "total_credits": [["total", "credits"], ["total", "deposits"], ["total", "credit"]],
                  "opening": [["opening", "balance"]], "closing": [["closing", "balance"]]}


def _norm(w: Word) -> str:
    return w.text.lower().strip(":")


def find_summary(lines_by_page: list[list[Line]], robust: bool, skip_dated: bool = False) -> dict[str, Decimal]:
    """Opening/closing/total labels. Pass 1: value on the same line. Pass 2 (robust only): value printed
    under the label (summary boxes), skipping the table's own header row."""
    out: dict[str, Decimal] = {}
    for pass_no in (1, 2):
        if pass_no == 2 and not robust:
            break
        for lines in lines_by_page:
            hdr = find_header(lines)
            hdr_i = hdr[0] if hdr else -1
            for li, ln in enumerate(lines):
                if pass_no == 2 and li == hdr_i:
                    continue
                if skip_dated and _leading_date(ln.words, 1e9)[0] is not None:
                    continue                     # a line that starts with a date is a transaction, not a summary
                ws = ln.words
                for key, aliases in _LABEL_ALIASES.items():
                    if key in out:
                        continue
                    for toks in aliases:
                        n = len(toks)
                        for i in range(len(ws) - n + 1):
                            if [_norm(w) for w in ws[i:i + n]] != toks:
                                continue
                            lab = ws[i:i + n]
                            val = None
                            if pass_no == 1:
                                for w in ws[i + n:]:
                                    if _norm(w) in ("total", "opening", "closing"):
                                        break
                                    a = parse_amount(w.text.strip(":"))
                                    if a and _has_decimals(a):
                                        val = balance_value(a)
                                        break
                            elif li + 1 < len(lines):
                                lx0, lx1 = lab[0].x0, lab[-1].x1
                                nxt = lines[li + 1]
                                if nxt.y - ln.y < 30:
                                    best = None
                                    for w in nxt.words:
                                        a = parse_amount(w.text)
                                        if not (a and _has_decimals(a)):
                                            continue
                                        d = min(abs(w.x0 - lx0), abs(w.x1 - lx1), abs(w.xc - (lx0 + lx1) / 2))
                                        if d < 45 and (best is None or d < best[0]):
                                            best = (d, balance_value(a))
                                    if best:
                                        val = best[1]
                            if val is not None:
                                out[key] = val
                            break
                        if key in out:
                            break
    return out


# ----------------------------------------------------------------------------- result helper
def _stmt_from_rows(name: str, pages: int, rows: list[Txn], summ: dict[str, Decimal], mode: str,
                    notes: list[str]) -> Statement:
    for i, t in enumerate(rows):
        t.idx = i
    return Statement(source_name=name, page_count=pages, opening=summ.get("opening"), closing=summ.get("closing"),
                     declared_total_debits=summ.get("total_debits"), declared_total_credits=summ.get("total_credits"),
                     txns=rows, mode=mode, layout_notes=notes)


def _join(words: list[Word]) -> str:
    return " ".join(w.text for w in sorted(words, key=lambda w: w.x0))


# ============================================================================= BASELINE
def extract_baseline(doc: pymupdf.Document, name: str = "") -> Statement:
    pages, _ = read_words(doc, drop_oversized=False)
    lines_by_page = [group_lines(p) for p in pages]
    rows: list[Txn] = []
    notes: list[str] = []
    summ = find_summary(lines_by_page, robust=False)
    cols: list[HCell] | None = None
    for pno, lines in enumerate(lines_by_page, start=1):
        h = find_header(lines)
        start = 0
        if h:
            start, cols = h[0] + 1, h[1]
        elif cols is None:
            continue
        if cols is None:
            continue
        cols_sorted = sorted(cols, key=lambda c: c.xc)
        mids = [(a.xc + b.xc) / 2 for a, b in zip(cols_sorted, cols_sorted[1:])]

        def col_of(w: Word) -> HCell:
            k = sum(w.xc > m for m in mids)
            return cols_sorted[k]

        for ln in lines[start:]:
            low = ln.text.lower()
            cells: dict[str, list[Word]] = {}
            for w in ln.words:
                cells.setdefault(col_of(w).role or "", []).append(w)
            narr = _join(cells.get("narration", []))
            bal_txt = _join(cells.get("balance", []))
            if OPENING.search(narr.lower()) and bal_txt:
                a = parse_amount(bal_txt)
                if a:
                    summ.setdefault("opening", balance_value(a))
                continue
            if CLOSING.search(narr.lower()) and bal_txt:
                a = parse_amount(bal_txt)
                if a:
                    summ["closing"] = balance_value(a)
                break
            if "closing balance" in low or "end of statement" in low:
                break
            d = parse_date(_join(cells.get("date", [])))
            if d is not None:
                t = Txn(idx=0, page=pno, date=d, date_text=_join(cells["date"]), description=narr,
                        source_text=ln.text, bbox=ln.bbox)
                vd = _join(cells.get("value_date", []))
                t.value_date = parse_date(vd) if vd else None
                t.ref = _join(cells.get("ref", [])) or None
                _fill_amounts_baseline(t, cells)
                rows.append(t)
            elif rows and narr:
                rows[-1].description += " " + narr
                rows[-1].source_text += " | " + ln.text
    if cols is None:
        notes.append("no recognizable table header")
    return _stmt_from_rows(name, len(doc), rows, summ, "baseline", notes)


def _fill_amounts_baseline(t: Txn, cells: dict[str, list[Word]]) -> None:
    def num(role: str):
        txt = _join(cells.get(role, []))
        if not txt:
            return None, ""
        a = parse_amount(txt)
        return (a if a and _has_decimals(a) else None), txt

    for role in ("debit", "credit", "amount", "balance"):
        a, txt = num(role)
        if txt:
            t.raw[role] = txt
        if a is None:
            continue
        if role == "debit":
            t.debit = a.value
        elif role == "credit":
            t.credit = a.value
        elif role == "balance":
            t.balance = balance_value(a)
        elif role == "amount":
            ind = _join(cells.get("indicator", [])).lower()
            if a.suffix == "Dr" or ind in DR_WORDS or a.negative:
                t.debit = a.value
            elif a.suffix == "Cr" or ind in CR_WORDS:
                t.credit = a.value


# ============================================================================= ROBUST
@dataclass
class Cluster:
    role: str | None
    edge: str               # 'x1' or 'x0'
    xs: list[float] = field(default_factory=list)
    x0: float = 1e9
    x1: float = -1e9
    n: int = 0

    @property
    def pos(self) -> float:
        return statistics.median(self.xs)


def _cluster(tokens: list[Word], edge: str, tol: float = 2.5) -> list[Cluster]:
    key = (lambda w: w.x1) if edge == "x1" else (lambda w: w.x0)
    out: list[Cluster] = []
    for w in sorted(tokens, key=key):
        if out and key(w) - out[-1].xs[-1] <= tol:
            c = out[-1]
        else:
            c = Cluster(None, edge)
            out.append(c)
        c.xs.append(key(w))
        c.x0, c.x1, c.n = min(c.x0, w.x0), max(c.x1, w.x1), c.n + 1
    return out


def _merge_suffix_words(lines: list[Line]) -> None:
    """'2,551.47' + 'Dr' -> one word '2,551.47 Dr'."""
    for ln in lines:
        out: list[Word] = []
        for w in ln.words:
            if out and w.text.lower().rstrip(".") in ("dr", "cr") and w.x0 - out[-1].x1 < 6 and \
                    (parse_amount(out[-1].text) or looks_numericish(out[-1].text)):
                p = out[-1]
                out[-1] = Word(p.x0, min(p.y0, w.y0), w.x1, max(p.y1, w.y1), p.text + " " + w.text, p.page)
            else:
                out.append(w)
        ln.words = out


def extract_robust(doc: pymupdf.Document, name: str = "", fixes: bool = False) -> Statement:
    """fixes=False is the behaviour frozen in bench/LOCK.json. fixes=True adds two post-lock fixes (see docs/RESULTS.md)."""
    pages, dropped = read_words(doc, drop_oversized=True)
    lines_by_page = [group_lines(p) for p in pages]
    for lines in lines_by_page:
        _merge_suffix_words(lines)
    notes: list[str] = []
    if dropped:
        notes.append(f"ignored {dropped} oversized/rotated (watermark-like) words")

    # --- 1. table regions
    headers = [find_header(lines) for lines in lines_by_page]
    first_h = next((h for h in headers if h), None)
    regions: list[list[Line]] = []
    for lines, h in zip(lines_by_page, headers):
        if h:
            regions.append(lines[h[0] + 1:])
        else:
            k = next((i for i, ln in enumerate(lines) if _leading_date(ln.words, 1e9)[0]), None)
            regions.append(lines[k:] if k is not None else [])
    hdr_cells = first_h[1] if first_h else None

    # --- 2. numeric clusters from clean numeric tokens
    toks: list[Word] = []
    toks_body: list[Word] = []          # same, minus opening/closing/carry-forward label lines
    for reg in regions:
        for ln in reg:
            low_ln = ln.text.lower()
            if FURNITURE.search(low_ln):
                continue
            is_label = bool(OPENING.search(low_ln) or CLOSING.search(low_ln) or FWD.search(low_ln))
            for w in ln.words:
                a = parse_amount(w.text)
                if a and _has_decimals(a) and a.grouping_ok:
                    toks.append(w)
                    if not is_label:
                        toks_body.append(w)

    def pick(tokens: list[Word], min_n: int) -> list[Cluster]:
        cr_ = [c for c in _cluster(tokens, "x1") if c.n >= min_n]
        cl_ = [c for c in _cluster(tokens, "x0") if c.n >= min_n]
        return cr_ if (len(cr_) <= len(cl_) or not cl_) else cl_

    clusters = pick(toks, 3)
    if fixes and hdr_cells:
        # short statements: a column with only 1-2 entries (e.g. two debits, one credit) is still a column
        # when the header says it exists
        n_roles = sum(1 for c in hdr_cells if c.role in NUMERIC_ROLES)
        if len(clusters) < n_roles:
            relaxed = pick(toks_body, 1)
            if len(relaxed) == n_roles:
                clusters = relaxed
    clusters = sorted(clusters, key=lambda c: c.pos)
    if not clusters:
        notes.append("no numeric columns found")
        return _stmt_from_rows(name, len(doc), [], find_summary(lines_by_page, True), "robust", notes)

    # --- 3. roles for clusters
    role_note = _assign_roles(clusters, hdr_cells, regions, notes, fixes)

    summ = find_summary(lines_by_page, robust=True, skip_dated=fixes)
    rows: list[Txn] = []
    cur: Txn | None = None
    cur_last_y: float | None = None
    by_role = {c.role: c for c in clusters if c.role}
    first_num_x = min(c.x0 for c in clusters)

    ind_cell = next((c for c in (hdr_cells or []) if c.role == "indicator"), None)
    ref_cell = next((c for c in (hdr_cells or []) if c.role == "ref"), None)

    def aligned(w: Word) -> Cluster | None:
        if not looks_numericish(w.text):
            return None
        for c in clusters:
            e = w.x1 if c.edge == "x1" else w.x0
            if abs(e - c.pos) <= 3.0:
                return c
        return None

    for pno, reg in enumerate(regions, start=1):
        cur, cur_last_y = None, None  # a wrapped row never continues across a page break
        page_pitch = None
        ys = [ln.y for ln in reg if not FURNITURE.search(ln.text.lower())]
        if len(ys) > 2:
            gaps = sorted(b - a for a, b in zip(ys, ys[1:]) if b - a > 1)
            page_pitch = gaps[0] if gaps else None
        for ln in reg:
            low = ln.text.lower()
            if FURNITURE.search(low) and not (OPENING.search(low) or CLOSING.search(low)):
                continue
            num_words: dict[str, Word] = {}
            rest: list[Word] = []
            for w in ln.words:
                c = aligned(w)
                if c is not None and c.role:
                    num_words[c.role] = w
                else:
                    rest.append(w)
            # label rows: opening / closing / carry-forward. With fixes=True a line that carries a debit/credit
            # amount is a transaction even if its narration says "closing balance transfer"
            label_row = not (fixes and any(r in num_words for r in ("debit", "credit", "amount")))
            if label_row and OPENING.search(low) and "balance" in num_words:
                a = parse_amount(num_words["balance"].text)
                if a:
                    summ["opening"] = balance_value(a)
                continue
            if label_row and CLOSING.search(low) and "balance" in num_words:
                a = parse_amount(num_words["balance"].text)
                if a:
                    summ["closing"] = balance_value(a)
                cur = None
                continue
            if FWD.search(low) and set(num_words) <= {"balance"}:
                cur = None
                continue
            if label_row and (CLOSING.search(low) or "end of statement" in low):
                cur = None
                continue
            d, vd, consumed = _leading_date(rest, first_num_x)
            body = [w for w in rest if w not in consumed]
            if d is not None or num_words and any(r in num_words for r in ("debit", "credit", "amount")):
                if d is None:  # blank-date row: inherits the previous date
                    prev = rows[-1] if rows else None
                    d = prev.date if prev else None
                    dtxt = ""
                    notes_row = ["date inherited from previous row (blank date cell)"]
                else:
                    dtxt = " ".join(w.text for w in consumed[:3])
                    notes_row = []
                desc_words, ref_words, ind_words = [], [], []
                for w in body:
                    if ref_cell and ref_cell.x0 - 3 <= w.x0 < ref_cell.x1 + 25 and w.xc > ref_cell.x0 - 3:
                        ref_words.append(w)
                    elif (ind_cell and ind_cell.x0 - (30 if fixes else 6) <= w.x0 <= ind_cell.x1 + 20
                          and w.text.lower() in DR_WORDS | CR_WORDS):
                        ind_words.append(w)
                    elif not ind_cell and w.text.lower() in DR_WORDS | CR_WORDS and "amount" in by_role \
                            and w.x1 < first_num_x + 1 and w.x0 > first_num_x - 80:
                        ind_words.append(w)
                    else:
                        desc_words.append(w)
                t = Txn(idx=0, page=pno, date=d, date_text=dtxt, value_date=vd, description=_join(desc_words),
                        ref=_join(ref_words) or None, source_text=ln.text, bbox=ln.bbox, notes=notes_row)
                _fill_amounts_robust(t, num_words, ind_words)
                rows.append(t)
                cur, cur_last_y = t, ln.y
            elif cur is not None and body and not num_words:
                limit = (page_pitch or 11.5) * 1.75
                if ln.y - (cur_last_y or ln.y) <= limit:
                    cur.description += " " + _join(body)
                    cur.source_text += " | " + ln.text
                    x0, y0, x1, y1 = ln.bbox
                    bx = cur.bbox or ln.bbox
                    cur.bbox = (min(bx[0], x0), min(bx[1], y0), max(bx[2], x1), max(bx[3], y1))
                    cur_last_y = ln.y
                else:
                    cur = None
            else:
                cur = None
    notes.extend(role_note)
    return _stmt_from_rows(name, len(doc), rows, summ, "robust", notes)


def _leading_date(words: list[Word], limit_x: float) -> tuple:
    """Longest run of leading words (left of first numeric column) that parses as a date; plus value date."""
    lead = [w for w in words if w.x1 <= limit_x + 1][:8]
    for k in (3, 2, 1):
        if len(lead) >= k:
            d = parse_date(" ".join(w.text for w in lead[:k]))
            if d:
                consumed = list(lead[:k])
                vd = None
                for k2 in (3, 2, 1):
                    if len(lead) >= k + k2:
                        vd = parse_date(" ".join(w.text for w in lead[k:k + k2]))
                        if vd:
                            consumed += lead[k:k + k2]
                            break
                return d, vd, consumed
    return None, None, []


def _assign_roles(clusters: list[Cluster], hdr: list[HCell] | None, regions: list[list[Line]],
                  notes: list[str], fixes: bool = False) -> list[str]:
    n = len(clusters)
    out: list[str] = []
    if hdr:
        nroles = [c for c in sorted(hdr, key=lambda c: c.xc) if c.role in NUMERIC_ROLES]
        if len(nroles) == n:
            for c, h in zip(clusters, nroles):
                c.role = h.role
            return out
        for c in clusters:  # nearest header cell on the numeric side
            span = (c.x0 + c.x1) / 2
            best = min(nroles, key=lambda h: abs(h.xc - span), default=None)
            c.role = best.role if best else None
        out.append("numeric columns matched to headers by proximity (counts differ)")
        # drop duplicate role assignments: keep the denser cluster
        seen: dict[str, Cluster] = {}
        for c in sorted(clusters, key=lambda c: -c.n):
            if c.role in seen:
                c.role = None
            else:
                seen[c.role] = c
        return out
    # ---- header-free structural fallback
    out.append("header not recognised: structural column inference")
    n_rows = max(1, sum(1 for r in regions for ln in r if _leading_date(ln.words, 1e9)[0]))
    if fixes:  # rows with a blank date cell still count as rows
        def _numeric_line(ln: Line) -> bool:
            for w in ln.words:
                a = parse_amount(w.text)
                if a and _has_decimals(a) and a.grouping_ok and any(
                        abs((w.x1 if c.edge == "x1" else w.x0) - c.pos) <= 3 for c in clusters):
                    return True
            return False
        n_rows = max(1, sum(_numeric_line(ln) for r in regions for ln in r))
    dens = [c.n / n_rows for c in clusters]
    if n == 1:
        clusters[0].role = "amount"
    elif n == 2:
        # (debit, credit) are mutually exclusive and sparse; (amount, balance) are both dense
        if dens[0] + dens[1] <= 1.25 and dens[1] < 0.9:
            clusters[0].role, clusters[1].role = "debit", "credit"
            out.append("debit/credit order assumed left->right (verified by reconciliation)")
        else:
            clusters[0].role, clusters[1].role = "amount", "balance"
    elif n == 3 and dens[2] > 0.8:
        clusters[0].role, clusters[1].role, clusters[2].role = "debit", "credit", "balance"
        out.append("debit/credit order assumed left->right (verified by reconciliation)")
    else:
        notes.append("column structure ambiguous")
    return out


def _fill_amounts_robust(t: Txn, nw: dict[str, Word], ind_words: list[Word]) -> None:
    for role in ("debit", "credit", "amount", "balance"):
        w = nw.get(role)
        if w is None:
            continue
        t.raw[role] = w.text
        a = parse_amount(w.text)
        problem = "unparseable" if a is None else ("bad_grouping" if not a.grouping_ok else "")
        if role == "amount":
            ind = ind_words[0].text.lower() if ind_words else ""
            m = re.search(r"\b(dr|cr)\.?$", w.text.lower())
            suffix = m.group(1) if m else (a.suffix.lower() if a and a.suffix else "")
            if suffix == "dr" or ind in DR_WORDS or w.text.strip().startswith("-"):
                t.raw["_dir"] = "debit"
            elif suffix == "cr" or ind in CR_WORDS:
                t.raw["_dir"] = "credit"
            else:
                t.raw["_dir"] = ""
        if problem:
            t.notes.append(f"{role}: {problem} token '{w.text}'")
            continue
        if role == "debit":
            t.debit = a.value
        elif role == "credit":
            t.credit = a.value
        elif role == "balance":
            t.balance = balance_value(a)
        else:
            d = t.raw["_dir"]
            if d == "debit":
                t.debit = a.value
            elif d == "credit":
                t.credit = a.value
            else:
                t.notes.append("direction_unknown")
                t.raw["amount_value"] = str(a.value)
