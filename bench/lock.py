"""Benchmark lock: freeze fixture ground truth and pipeline source before the final holdout comparison.

    python -m bench.lock            # (re)write bench/LOCK.json  -- do this once, BEFORE the holdout run
    python -m bench.lock --verify   # check fixtures and pipeline code still match the lock

Post-lock changes are listed in LOCK.json ("post_lock_changes"). Arm 3 (`full`) runs the locked behaviour
(`fixes=False`); arm 3b (`full_fixed`) includes the post-lock fixes and is reported separately as optimistic.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from .make_fixtures import build, digest

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "bench" / "LOCK.json"
CODE_FILES = ["models.py", "money.py", "extract.py", "recover.py", "validate.py", "pipeline.py"]


def code_hashes() -> dict[str, str]:
    return {f: hashlib.sha256((ROOT / "statement_guard" / f).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for f in CODE_FILES}


def code_digest() -> str:
    return hashlib.sha256(json.dumps(code_hashes(), sort_keys=True).encode()).hexdigest()


def fixture_digests() -> dict:
    out = {}
    for sp in ("dev", "holdout"):
        fx = build(sp)
        out[sp] = {"n": len(fx), "truth_sha256": digest(fx)}
    return out


def write() -> dict:
    lock = {"locked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "fixtures": fixture_digests(), "code_sha256": code_digest(), "code_files": code_hashes()}
    LOCK.write_text(json.dumps(lock, indent=1), encoding="utf-8")
    return lock


def verify() -> dict:
    lock = json.loads(LOCK.read_text())
    return {"fixtures_match": lock["fixtures"] == fixture_digests(),
            "code_identical_to_lock": lock["code_sha256"] == code_digest(),
            "post_lock_changes": len(lock.get("post_lock_changes", [])),
            "locked_at_utc": lock["locked_at_utc"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite an existing lock (invalidates the holdout)")
    a = ap.parse_args()
    if a.verify:
        r = verify()
        print(r)
        raise SystemExit(0 if r["fixtures_match"] else 1)
    if LOCK.exists() and not a.force:
        raise SystemExit("LOCK.json already exists; refusing to overwrite (use --force and say so in the results).")
    l = write()
    print("locked:", l["locked_at_utc"], "code", l["code_sha256"][:12], {k: v["n"] for k, v in l["fixtures"].items()})
