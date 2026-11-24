"""Charts and the architecture diagram for the deck/docs, drawn from results/*.json.

    python -m bench.charts      # writes docs/img/*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)

# documented reference palette (light surface): blue = slot 1, red = slot 8, neutral gray for 'sent to review'
BLUE, RED, GRAY = "#2a78d6", "#e34948", "#a9a8a2"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e3e2dd"
plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "axes.edgecolor": GRID, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "figure.dpi": 100})


def _clean(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)


def outcomes(ev: dict, arm: str) -> tuple[int, int, int]:
    cs = ev["per_case"][arm]
    ok = sum(c["accepted"] and not c["positive"] for c in cs)
    silent = sum(c["accepted"] and c["positive"] for c in cs)
    flagged = sum(c["flagged"] for c in cs)
    return ok, flagged, silent


def chart_outcomes(ev: dict) -> None:
    arms = [("baseline", "Baseline parser\n(no checks)"), ("validated", "Baseline +\nvalidation"),
            ("full", "Full pipeline\n(locked)")]
    fig, ax = plt.subplots(figsize=(7.4, 3.3))
    y = list(range(len(arms)))[::-1]
    for yi, (arm, label) in zip(y, arms):
        ok, fl, bad = outcomes(ev, arm)
        left = 0
        for v, col, nm in ((ok, BLUE, "imported, correct"), (fl, GRAY, "sent to review"), (bad, RED, "imported, WRONG")):
            if v:
                ax.barh(yi, v, left=left, color=col, height=0.56, edgecolor="white", linewidth=2)
                ax.text(left + v / 2, yi, str(v), ha="center", va="center", fontsize=11, fontweight="bold",
                        color="white" if col != GRAY else INK)
            left += v
    ax.set_yticks(y, [a[1] for a in arms], fontsize=10)
    ax.set_xlim(0, 100)
    ax.set_xlabel("held-out statements (n = 100)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _clean(ax)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label="imported, correct"), Patch(color=GRAY, label="sent to review"),
                       Patch(color=RED, label="imported, WRONG (silent)")], loc="upper center",
              bbox_to_anchor=(0.5, 1.2), ncol=3, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "outcomes.png", dpi=200)
    plt.close(fig)


def chart_layouts(ev: dict) -> None:
    layouts = list(ev["arms"]["full"]["by_layout"].keys())
    fig, ax = plt.subplots(figsize=(7.4, 3.2))
    w = 0.38
    xs = range(len(layouts))
    for off, arm, col, nm in ((-w / 2, "baseline", GRAY, "Baseline parser"), (w / 2, "full", BLUE, "Full pipeline (locked)")):
        vals = []
        for lay in layouts:
            d = ev["arms"][arm]["by_layout"][lay]
            vals.append(100 * d["fin_exact"] / d["n"])
        bars = ax.bar([x + off for x in xs], vals, w * 0.92, color=col, label=nm, edgecolor="white", linewidth=1.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}", ha="center", fontsize=8.5, color=INK2)
    seen = {"A", "C"}
    ax.set_xticks(list(xs), [f"{l}{'' if l in seen else ' (unseen)'}" for l in layouts], fontsize=9)
    ax.set_ylim(0, 112)
    ax.set_ylabel("% of statements fully correct")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _clean(ax)
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, 1.17), ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "layouts.png", dpi=200)
    plt.close(fig)


def chart_injection(inj: dict) -> None:
    names = []
    for v in inj["cells"].values():
        if v["error"] not in names:
            names.append(v["error"])
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    h = 0.36
    y = list(range(len(names)))[::-1]
    for off, key, col, nm in ((h / 2, "running balance", BLUE, "statement has a running balance"),
                              (-h / 2, "opening/closing only", GRAY, "opening/closing balance only")):
        for yi, n in zip(y, names):
            c = inj["cells"].get(f"{n} | {key}")
            if not c:
                continue
            v = 100 * c["k"] / c["n"]
            ax.barh(yi + off, v, h * 0.9, color=col, edgecolor="white", linewidth=1.2, label=nm)
            ax.text(v + 1.5, yi + off, f"{v:.0f}%", va="center", fontsize=8.5, color=INK2)
    hs, ls = ax.get_legend_handles_labels()
    uniq = dict(zip(ls, hs))
    ax.legend(uniq.values(), uniq.keys(), frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.45, 1.13), ncol=2)
    ax.set_yticks(y, names, fontsize=9)
    ax.set_xlim(0, 112)
    ax.set_xlabel("% of injected errors routed to review (300 per cell)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _clean(ax)
    fig.tight_layout()
    fig.savefig(OUT / "injection.png", dpi=200)
    plt.close(fig)


def architecture() -> None:
    fig, ax = plt.subplots(figsize=(11.8, 4.7))
    ax.set_xlim(0, 117)
    ax.set_ylim(-1, 47)
    ax.axis("off")
    W, H1, H2 = 17, 18, 18

    def box(x, y, title, sub, fc="#eef3fb", ec=BLUE):
        ax.add_patch(FancyBboxPatch((x, y), W, H1, boxstyle="round,pad=0.3,rounding_size=1.2", fc=fc, ec=ec, lw=1.4))
        ax.text(x + W / 2, y + H1 - 2.6, title, ha="center", va="top", fontsize=10.5, fontweight="bold", color=INK)
        ax.text(x + W / 2, y + H1 - 7.2, sub, ha="center", va="top", fontsize=8, color=INK2, linespacing=1.4)

    def arrow(x0, y0, x1, y1, color=INK2, rad=0.0):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=13, lw=1.5, color=color,
                                     connectionstyle=f"arc3,rad={rad}"))

    xs = [1, 20.5, 40, 59.5, 79, 98.5]
    y1, y2 = 25, 2
    box(xs[0], y1, "PDF in", "untrusted upload\nsize / page / word caps\nencrypted or image-only\n-> UNSUPPORTED", "#f4f3ef", "#a9a8a2")
    box(xs[1], y1, "1 Extract", "PyMuPDF words + x,y\nlines and table region\nnumeric columns learned\nfrom the data; furniture\nand watermark dropped")
    box(xs[2], y1, "2 Normalize", "Decimal money\nday-first dates, Dr/Cr\nIndian grouping\nkeep page, bbox,\nsource text per row")
    box(xs[3], y1, "3 Validate", "open + cr - dr = close\nrunning-balance chain\ndeclared totals\ndate order, layout bleed")
    box(xs[4], y1, "4 Recover", "bounded, evidence-gated:\nOCR confusables, implied\namount/balance, direction\nevery repair is logged")
    box(xs[5], y1, "5 Route", "READY\nREADY_AUTOFIXED\nNEEDS_REVIEW\nUNSUPPORTED", "#fff6e5", "#eda100")
    box(xs[4], y2, "6 Reviewer UI", "suspect row + PDF crop\nwhy it was flagged\nedit, then re-validate\nonly a clean result unlocks", "#fdeeee", RED)
    box(xs[5], y2, "7 Export", "import-ready JSON / CSV\n(AA-shaped) only if READY*\notherwise diagnostics only", "#eaf6f0", "#1baf7a")
    for i in range(5):
        arrow(xs[i] + W + 0.4, y1 + 9, xs[i + 1] - 0.4, y1 + 9)
    arrow(xs[5] + 3, y1 - 0.4, xs[5] + 3, y2 + H2 + 0.4, color="#1baf7a")
    ax.text(xs[5] + 4, 22.3, "READY*", fontsize=8, color="#1b7a57")
    arrow(xs[5] + 1, y1 - 0.4, xs[4] + W - 2, y2 + H2 + 0.4, color=RED)
    ax.text(xs[4] + W - 4, 22.5, "review", fontsize=8, color=RED, ha="right")
    arrow(xs[4] + 2, y2 + H2 + 0.4, xs[3] + 9, y1 - 0.4, color=RED, rad=-0.15)
    ax.text(xs[4] - 1.5, 17.5, "fix, then the same checks run again", fontsize=8, color=RED, ha="right")
    ax.text(58, 45, "Statement Guard: every number is checked against the statement itself before it is imported",
            ha="center", fontsize=11.5, fontweight="bold")
    ax.text(xs[0], 8, "Not built: OCR (image-only files are\nrouted to review, never guessed)", fontsize=8.5, color=INK2)
    fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    ev = json.loads((ROOT / "results" / "eval_holdout.json").read_text(encoding="utf-8"))
    inj = json.loads((ROOT / "results" / "injection.json").read_text(encoding="utf-8"))
    chart_outcomes(ev)
    chart_layouts(ev)
    chart_injection(inj)
    architecture()
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
