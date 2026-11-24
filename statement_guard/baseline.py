"""Baseline v1: the 'straightforward parser' we benchmark against. Our own reproduction, written for this
benchmark; it makes no claim about how any production importer behaves.

What a competent quick parser does:
  * find the table header by keywords (same lexicon as the full pipeline);
  * on each following line, money tokens (digits with decimals, optional Dr/Cr) go to the nearest numeric
    header; every other word is narration;
  * a row starts where the line begins with a parseable date; other lines are wrapped narration;
  * opening/closing balance from 'Opening Balance: x' style labels or opening/closing rows in the table.

What it does not do (and the full pipeline does): learn columns from the data, drop page furniture and
watermarks, treat a line with amounts but no date as a row, read label-above-value summary boxes, or run
without a recognised header.
"""
from __future__ import annotations

import pymupdf

from .extract import (CLOSING, CR_WORDS, DR_WORDS, NUMERIC_ROLES, OPENING, HCell, Word, _has_decimals,
                      _leading_date, _stmt_from_rows, balance_value, find_header, find_summary, group_lines,
                      read_words)
from .models import Statement, Txn
from .money import parse_amount


def _interval_dist(w: Word, c: HCell) -> float:
    if w.x1 < c.x0:
        return c.x0 - w.x1
    if w.x0 > c.x1:
        return w.x0 - c.x1
    return 0.0


def _split_words(words: list[Word]) -> tuple[list[tuple[Word, object]], list[Word]]:
    """(numeric tokens with parsed amount, other words); a trailing Dr/Cr word is glued to the amount."""
    nums, rest = [], []
    for w in words:
        a = parse_amount(w.text)
        if a and _has_decimals(a):
            nums.append((w, a))
        elif nums and w.text.lower().rstrip(".") in ("dr", "cr") and w.x0 - nums[-1][0].x1 < 6:
            pw, pa = nums[-1]
            glued = parse_amount(pw.text + w.text.lower().rstrip("."))
            nums[-1] = (Word(pw.x0, pw.y0, w.x1, pw.y1, pw.text + " " + w.text, pw.page), glued or pa)
        else:
            rest.append(w)
    return nums, rest


def extract_baseline(doc: pymupdf.Document, name: str = "") -> Statement:
    pages, _ = read_words(doc, drop_oversized=False)
    lines_by_page = [group_lines(p) for p in pages]
    summ = find_summary(lines_by_page, robust=False)
    rows: list[Txn] = []
    cols: list[HCell] | None = None
    notes: list[str] = []
    for pno, lines in enumerate(lines_by_page, start=1):
        h = find_header(lines)
        if h:
            start, cols = h[0] + 1, h[1]
        elif cols is None:
            continue
        else:
            start = 0
        num_cols = [c for c in cols if c.role in NUMERIC_ROLES]
        ref_col = next((c for c in cols if c.role == "ref"), None)
        ind_col = next((c for c in cols if c.role == "indicator"), None)
        for ln in lines[start:]:
            low = ln.text.lower()
            nums, rest = _split_words(ln.words)
            if OPENING.search(low) and nums:
                summ.setdefault("opening", balance_value(nums[-1][1]))
                continue
            if CLOSING.search(low) or "end of statement" in low:
                if nums and CLOSING.search(low):
                    summ["closing"] = balance_value(nums[-1][1])
                break
            d, vd, consumed = _leading_date(rest, 1e9)
            body = [w for w in rest if w not in consumed]
            if d is not None:
                ind_w = next((w for w in body if ind_col and w.text.lower() in DR_WORDS | CR_WORDS
                              and ind_col.x0 - 30 <= w.x0 <= ind_col.x1 + 20), None)
                ind = ind_w.text.lower() if ind_w else ""
                desc, ref = [], []
                for w in body:
                    if ref_col and ref_col.x0 - 3 <= w.xc <= ref_col.x1 + 25:
                        ref.append(w)
                    elif w is ind_w:
                        continue
                    else:
                        desc.append(w)
                t = Txn(idx=0, page=pno, date=d, date_text=" ".join(w.text for w in consumed[:3]), value_date=vd,
                        description=" ".join(w.text for w in desc), ref=" ".join(w.text for w in ref) or None,
                        source_text=ln.text, bbox=ln.bbox)
                for w, a in nums:
                    if not num_cols:
                        continue
                    col = min(num_cols, key=lambda c: (_interval_dist(w, c), abs(w.xc - c.xc)))
                    t.raw[col.role] = w.text
                    if col.role == "debit":
                        t.debit = a.value
                    elif col.role == "credit":
                        t.credit = a.value
                    elif col.role == "balance":
                        t.balance = balance_value(a)
                    else:
                        if a.suffix == "Dr" or ind in DR_WORDS or a.negative:
                            t.debit = a.value
                        elif a.suffix == "Cr" or ind in CR_WORDS:
                            t.credit = a.value
                rows.append(t)
            elif rows and rest:
                rows[-1].description += " " + " ".join(w.text for w in rest)
                rows[-1].source_text += " | " + ln.text
    if cols is None:
        notes.append("no recognizable table header")
    return _stmt_from_rows(name, len(doc), rows, summ, "baseline", notes)
