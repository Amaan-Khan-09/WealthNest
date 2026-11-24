"""Exact-decimal parsing of Indian-style money and date tokens.

All money is `decimal.Decimal`; floats are never used for amounts.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

_AMT_RE = re.compile(
    r"""^(?P<cur>(?:Rs\.?|INR|₹)\s*)?
        (?P<neg>[-(])?
        (?P<num>\d[\d,]*(?:\.\d{1,2})?|\.\d{1,2})
        \)?\s*
        (?P<suf>Dr|Cr|DR|CR|dr|cr)?\.?$""",
    re.X,
)

# Characters an OCR engine / noisy text layer commonly confuses with digits.
OCR_CONFUSABLE = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8", "Z": "2"}


class Amount:
    """Parsed money token."""

    __slots__ = ("value", "suffix", "negative", "grouping_ok", "text")

    def __init__(self, value: Decimal, suffix: str | None, negative: bool, grouping_ok: bool, text: str):
        self.value = value
        self.suffix = suffix  # 'Dr' | 'Cr' | None
        self.negative = negative
        self.grouping_ok = grouping_ok
        self.text = text

    def __repr__(self) -> str:  # pragma: no cover
        return f"Amount({self.value}, {self.suffix}, neg={self.negative})"


def grouping_is_valid(int_part: str) -> bool:
    """True if commas follow Indian (2-2-3) or Western (3-3-3) grouping, or there are none."""
    if "," not in int_part:
        return True
    groups = int_part.split(",")
    if not groups[0] or len(groups[0]) > 3 or not groups[-1] or len(groups[-1]) != 3:
        return False
    mid = groups[1:-1]
    indian = len(groups[0]) <= 2 and all(len(g) == 2 for g in mid)
    western = all(len(g) == 3 for g in mid)
    return indian or western


def parse_amount(token: str) -> Amount | None:
    """Parse '1,23,456.78', '12,345.00Cr', '(500.00)', '-5,000.00', '₹ 10.5'. Returns None if not money."""
    t = token.strip()
    m = _AMT_RE.match(t)
    if not m:
        return None
    num = m.group("num")
    int_part = num.split(".")[0]
    try:
        value = Decimal(num.replace(",", ""))
    except InvalidOperation:
        return None
    neg = bool(m.group("neg"))
    suf = m.group("suf")
    suf = suf.capitalize() if suf else None
    return Amount(value, suf, neg, grouping_is_valid(int_part), t)


_STRICT_MONEY = re.compile(r"^\d[\d,]*\.\d{2}$")


def repair_ocr_amount(token: str) -> str | None:
    """Map confusable letters to digits inside a numeric-looking token.

    Only tokens made purely of digits, '.', ',' and confusable letters (with at least one real digit)
    are touched, and the result must be a well-formed two-decimal amount. Ordinary words are never changed.
    """
    t = token.strip()
    if not t or not any(c in OCR_CONFUSABLE for c in t):
        return None
    if not all(c.isdigit() or c in ".," or c in OCR_CONFUSABLE for c in t) or not any(c.isdigit() for c in t):
        return None
    fixed = "".join(OCR_CONFUSABLE.get(c, c) for c in t)
    return fixed if _STRICT_MONEY.match(fixed) else None


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

_DATE_NUM = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})$")
_DATE_ISO = re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$")
_DATE_MON = re.compile(r"^(\d{1,2})[\s/\-.]?([A-Za-z]{3,9})[\s/\-.,]*(\d{2}|\d{4})$")


def parse_date(text: str) -> date | None:
    """Day-first (Indian convention) date parser. Returns None if not a valid date."""
    t = text.strip()
    if not t:
        return None
    try:
        m = _DATE_ISO.match(t)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = _DATE_NUM.match(t)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            yy = int(y) + 2000 if len(y) == 2 else int(y)
            return date(yy, mo, d)
        m = _DATE_MON.match(t)
        if m:
            mon = _MONTHS.get(m.group(2)[:3].lower())
            if mon is None:
                return None
            y = m.group(3)
            yy = int(y) + 2000 if len(y) == 2 else int(y)
            return date(yy, mon, int(m.group(1)))
    except ValueError:
        return None
    return None


def fmt_indian(value: Decimal) -> str:
    """Format with Indian digit grouping, two decimals: 1234567.5 -> '12,34,567.50'."""
    neg = value < 0
    q = f"{abs(value):.2f}"
    ip, fp = q.split(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        ip = ",".join(parts) + "," + tail
    return ("-" if neg else "") + ip + "." + fp
