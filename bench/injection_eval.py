"""Validator-only benchmark: inject known errors directly into extracted *records* (no PDFs involved).

    python -m bench.injection_eval            # writes results/injection.json

Purpose: separate "can the checks see this error class at all?" from "does the parser make this error?".
Each error type is injected N times into fresh synthetic ledgers (seeded), with and without a running balance.
"""
from __future__ import annotations

import json
import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from statement_guard.models import Statement, Status, Txn
from statement_guard.validate import validate

from .generator import build_ledger
from .metrics import rate

ROOT = Path(__file__).resolve().parent.parent
D = Decimal


def stmt_from_ledger(rng: random.Random, with_balance: bool) -> Statement:
    opening, rows = build_ledger(rng, rng.randint(15, 60), wide=False, overdraft=False)
    txns = [Txn(idx=i, page=1, date=r.date, description=r.desc, debit=r.debit, credit=r.credit,
                balance=r.balance if with_balance else None, raw={"balance": "x"} if with_balance else {})
            for i, r in enumerate(rows)]
    return Statement(opening=opening, closing=rows[-1].balance, txns=txns)


def _reindex(s: Statement) -> None:
    for i, t in enumerate(s.txns):
        t.idx = i


def _amt(t: Txn) -> Decimal:
    return t.debit if t.debit is not None else t.credit


def _set_amt(t: Txn, v: Decimal) -> None:
    if t.debit is not None:
        t.debit = v
    else:
        t.credit = v


def inj_drop_row(s, rng):
    del s.txns[rng.randrange(1, len(s.txns) - 1)]


def inj_dup_row(s, rng):
    k = rng.randrange(1, len(s.txns) - 1)
    s.txns.insert(k + 1, s.txns[k].model_copy(deep=True))


def inj_flip_direction(s, rng):
    t = s.txns[rng.randrange(len(s.txns))]
    t.debit, t.credit = t.credit, t.debit


def inj_digit_change(s, rng):
    t = s.txns[rng.randrange(len(s.txns))]
    _set_amt(t, _amt(t) + D(rng.choice([1, 10, 100, 1000])) * rng.choice([1, 2, 3]))


def inj_transpose(s, rng):
    for _ in range(50):
        t = s.txns[rng.randrange(len(s.txns))]
        txt = f"{_amt(t):.2f}".replace(".", "")
        i = rng.randrange(len(txt) - 1)
        if txt[i] != txt[i + 1]:
            txt = txt[:i] + txt[i + 1] + txt[i] + txt[i + 2:]
            _set_amt(t, D(txt[:-2] + "." + txt[-2:]))
            return


def inj_offsetting_pair(s, rng):
    """+x on one row, -x on another row of the SAME direction: the totals are unchanged."""
    x = D(rng.choice([10, 100, 500]))
    for _ in range(50):
        i, j = rng.sample(range(len(s.txns)), 2)
        a, b = s.txns[i], s.txns[j]
        if (a.debit is None) == (b.debit is None) and _amt(b) > x:
            _set_amt(a, _amt(a) + x)
            _set_amt(b, _amt(b) - x)
            return


def inj_wrong_description(s, rng):
    t = s.txns[rng.randrange(len(s.txns))]
    t.description = t.description[::-1]


def inj_date_shift_in_order(s, rng):
    for _ in range(50):
        k = rng.randrange(1, len(s.txns) - 1)
        lo, hi = s.txns[k - 1].date, s.txns[k + 1].date
        if (hi - lo).days >= 1:
            new = lo + timedelta(days=rng.randint(0, (hi - lo).days))
            if new != s.txns[k].date:
                s.txns[k].date = new
                return


def inj_date_out_of_order(s, rng):
    k = rng.randrange(2, len(s.txns))
    s.txns[k].date = s.txns[k - 1].date - timedelta(days=rng.randint(2, 40))


def inj_balance_digit(s, rng):
    t = s.txns[rng.randrange(len(s.txns))]
    if t.balance is not None:
        t.balance += D(rng.choice([10, 100, 1000]))


INJECTORS = {
    "dropped row": inj_drop_row,
    "duplicated row": inj_dup_row,
    "debit/credit flipped": inj_flip_direction,
    "amount digit changed": inj_digit_change,
    "adjacent digits transposed": inj_transpose,
    "two offsetting amount errors": inj_offsetting_pair,
    "printed balance wrong": inj_balance_digit,
    "date out of order": inj_date_out_of_order,
    "date wrong but still in order": inj_date_shift_in_order,
    "description wrong": inj_wrong_description,
}


def run(n: int = 300, seed: int = 7) -> dict:
    out: dict = {"n_per_cell": n, "cells": {}}
    for with_balance in (True, False):
        for name, fn in INJECTORS.items():
            if name == "printed balance wrong" and not with_balance:
                continue
            caught = 0
            done = 0
            for k in range(n):
                rng = random.Random(seed * 100003 + k)
                s = stmt_from_ledger(rng, with_balance)
                before = [(t.date, t.description, t.debit, t.credit, t.balance) for t in s.txns]
                fn(s, rng)
                _reindex(s)
                after = [(t.date, t.description, t.debit, t.credit, t.balance) for t in s.txns]
                if before == after:
                    continue                      # injector could not change anything this time
                done += 1
                caught += validate(s).status == Status.NEEDS_REVIEW
            key = f"{name} | {'running balance' if with_balance else 'opening/closing only'}"
            out["cells"][key] = {"error": name, "layout": "running balance" if with_balance else "opening/closing only",
                                 **rate(caught, done)}
    return out


def main() -> None:
    res = run()
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "injection.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"{'error injected':34s} {'with running balance':>22s} {'opening/closing only':>22s}")
    for name in INJECTORS:
        a = res["cells"].get(f"{name} | running balance")
        b = res["cells"].get(f"{name} | opening/closing only")
        fa = f"{a['k']}/{a['n']} ({a['rate']:.0%})" if a else "-"
        fb = f"{b['k']}/{b['n']} ({b['rate']:.0%})" if b else "-"
        print(f"{name:34s} {fa:>22s} {fb:>22s}")


if __name__ == "__main__":
    main()
