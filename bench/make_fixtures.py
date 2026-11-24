"""Build the dev and holdout fixture sets deterministically.

    python -m bench.make_fixtures            # writes fixtures/dev and fixtures/holdout
    python -m bench.make_fixtures --check    # regenerate in memory and verify the lock hashes

Dev layouts (A-D) are used to build the parser. Holdout contains four layouts (E-H) the parser was
never developed against, plus fresh seeds of two dev layouts (A, C) as an in-distribution reference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .generator import CATEGORIES, Fixture, make_fixture, write_fixture

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

# 20-slot stratified deck so every category appears in every layout (weights ~ CATEGORIES)
DECK = (["clean"] * 6 + ["watermark"] * 2 + ["blank_date"] * 2 + ["wide_amounts"] * 2 + ["overdraft"] * 1 +
        ["ocr_noise"] * 3 + ["src_missing_row", "src_dup_row", "src_amount_tamper", "scan_only"])
assert len(DECK) == 20 and {c for c, _ in CATEGORIES} == set(DECK)

PLAN = {
    "dev": [("A", 14, 1000), ("B", 14, 2000), ("C", 14, 3000), ("D", 14, 4000)],
    "holdout": [("E", 20, 5000), ("F", 20, 6000), ("G", 20, 7000), ("H", 20, 8000),
                ("A", 10, 9000), ("C", 10, 9500)],
}


def build(split: str) -> list[Fixture]:
    out = []
    for layout, n, base in PLAN[split]:
        for i in range(n):
            seed = base + i
            cat = DECK[(i * 7 + (base // 1000)) % 20]   # fixed permutation, same for everyone
            out.append(make_fixture(layout, seed, cat))
    return out


def digest(fixtures: list[Fixture]) -> str:
    """Hash of ground truth + layout/seed/category (PDF bytes can vary between reportlab builds)."""
    h = hashlib.sha256()
    for fx in fixtures:
        h.update(json.dumps(fx.truth, sort_keys=True).encode())
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--split", choices=["dev", "holdout", "both"], default="both")
    a = ap.parse_args()
    splits = ["dev", "holdout"] if a.split == "both" else [a.split]
    lock = {}
    for sp in splits:
        fx = build(sp)
        lock[sp] = {"n": len(fx), "truth_sha256": digest(fx)}
        if not a.check:
            for f in fx:
                write_fixture(f, FIXTURES / sp)
        print(f"{sp}: {len(fx)} fixtures  truth_sha256={lock[sp]['truth_sha256'][:16]}")
    lock_path = ROOT / "bench" / "LOCK.json"
    if a.check:
        want = json.loads(lock_path.read_text())["fixtures"]
        for sp in splits:
            ok = want.get(sp, {}).get("truth_sha256") == lock[sp]["truth_sha256"]
            print(f"lock check {sp}: {'OK' if ok else 'MISMATCH'}")
            if not ok:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
