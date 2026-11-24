"""Render slides.html to PDF with headless Edge/Chrome, check the slide limit, and rasterise pages for inspection.

    python submission/deck/build_deck.py            # writes submission/TeamName_Tech.pdf
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "TeamName_Tech.pdf"      # rename to <YourTeam>_Tech.pdf once the team name is final
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
PATH_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "chrome"]


def find_browser() -> str | None:
    found = next((b for b in BROWSERS if Path(b).exists()), None)
    return found or next((p for p in map(shutil.which, PATH_NAMES) if p), None)


def main() -> int:
    exe = find_browser()
    if not exe:
        print("No Chromium-based browser found (install Chrome, Edge or Chromium)")
        return 1
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={OUT}",
           (HERE / "slides.html").as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    doc = pymupdf.open(OUT)
    n = len(doc)
    print(f"{OUT.name}: {n} pages, page size {doc[0].rect.width:.0f}x{doc[0].rect.height:.0f} pt")
    if n > 12:
        print("ERROR: more than 12 slides")
        return 1
    prev = HERE / "preview"
    prev.mkdir(exist_ok=True)
    for i, p in enumerate(doc, start=1):
        p.get_pixmap(dpi=70).save(prev / f"slide_{i:02d}.png")
    print("previews in", prev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
