"""Orchestration: PDF bytes -> Statement with a final status.

Modes (the demo and CLI default to ``full_fixed``):
  naive       first-draft parser that assigns every word to the nearest column (kept to show why it was replaced)
  baseline    straightforward parser (baseline.py), no validation: whatever it extracts is 'accepted'
  validated   the same baseline extraction + validation and review routing
  full        robust extraction + evidence-backed recovery + validation   (code frozen in bench/LOCK.json)
  full_fixed  `full` plus two fixes made after the holdout run exposed them (reported separately)
"""
from __future__ import annotations

import time
from pathlib import Path

from .baseline import extract_baseline
from .extract import UnsupportedPDF, extract_baseline as extract_naive, extract_robust, is_image_only, open_pdf
from .models import Flag, Status, Statement
from .recover import recover
from .validate import validate

MODES = ("naive", "baseline", "validated", "full", "full_fixed")


def _unsupported(name: str, reason: str, mode: str, pages: int = 0) -> Statement:
    return Statement(source_name=name, page_count=pages, status=Status.UNSUPPORTED, mode=mode,
                     flags=[Flag(code="unsupported", severity="error", message=reason)])


def process(src: bytes | str | Path, mode: str = "full_fixed", name: str = "") -> Statement:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    t0 = time.perf_counter()
    name = name or (Path(src).name if isinstance(src, (str, Path)) else "upload.pdf")
    try:
        doc = open_pdf(src)
    except UnsupportedPDF as e:
        st = _unsupported(name, str(e), mode)
        st.runtime_ms = (time.perf_counter() - t0) * 1000
        return st
    try:
        if mode not in ("naive", "baseline") and is_image_only(doc):
            st = _unsupported(name, "Image-only PDF (no text layer). OCR is not implemented in this prototype, "
                                    "so the statement is routed to review instead of guessing.", mode, len(doc))
        elif mode in ("naive", "baseline"):
            st = (extract_naive if mode == "naive" else extract_baseline)(doc, name)
            st.status = Status.READY          # no validation: whatever was extracted is imported
        elif mode == "validated":
            st = validate(extract_baseline(doc, name))
        else:
            st = validate(recover(extract_robust(doc, name, fixes=(mode == "full_fixed"))))
    finally:
        doc.close()
    st.mode = mode
    st.runtime_ms = (time.perf_counter() - t0) * 1000
    return st
