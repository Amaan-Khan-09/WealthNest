"""Command line: python -m statement_guard.cli statement.pdf [--mode full_fixed] [--json out.json] [--csv out.csv]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .export import to_csv, to_json
from .models import Status
from .pipeline import MODES, process


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="statement_guard", description="Extract and verify a bank-statement PDF.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--mode", choices=MODES, default="full_fixed")
    ap.add_argument("--json", type=Path, help="write the full structured result here")
    ap.add_argument("--csv", type=Path, help="write transactions as CSV here")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        data = a.pdf.read_bytes()
    except OSError as e:
        print(f"cannot read {a.pdf}: {e.strerror or e}", file=sys.stderr)
        return 1
    st = process(data, mode=a.mode, name=a.pdf.name)
    if a.json:
        a.json.write_text(to_json(st), encoding="utf-8")
    if a.csv:
        a.csv.write_text(to_csv(st), encoding="utf-8")
    if not a.quiet:
        print(f"{a.pdf.name}: {st.status.value}  rows={len(st.txns)}  verification={st.verification_level}  "
              f"opening={st.opening}  closing={st.closing}  ({st.runtime_ms:.0f} ms)")
        for r in st.repairs:
            print(f"  repaired row {None if r.row_idx is None else r.row_idx + 1}: {r.kind} {r.before!r} -> {r.after!r}  [{r.evidence}]")
        for f in st.errors()[:15]:
            where = "" if f.row_idx is None else f" row {f.row_idx + 1}:"
            print(f"  FLAG{where} {f.code}: {f.message}")
        if len(st.errors()) > 15:
            print(f"  ... {len(st.errors()) - 15} more flags")
    return 0 if st.status in (Status.READY, Status.READY_AUTOFIXED, Status.READY_REVIEWED) else 2


if __name__ == "__main__":
    sys.exit(main())
