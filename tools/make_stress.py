#!/usr/bin/env python3
"""
make_stress.py — build a runnable stress variant from the PRODUCTION game.js.

Why a generated copy instead of editing game.js directly:
the shipped file must stay free of test scaffolding, but the stress run still
has to execute the real code. So the variant is produced by mechanical
substitution of exactly two things and nothing else:

  1. the `sleep` helper ignores its delay  (macrotask yield only)
  2. TUNING animation durations go to 0    (no per-frame waiting)
  3. the two game-transition setTimeouts go to 40ms
     (1500ms win delay + 1600ms interstitial = 3.1s per game boundary, so a
      9-game tournament burns ~28s in transitions alone and blows any deadline)

Everything else — board tables, geometry, snake rendering, tournament state
machine, the validator, every invariant-bearing function — is byte-identical
to what ships. The diff is asserted at the end so this cannot silently drift.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src", "game.js")
OUT_DIR = os.path.join(ROOT, "stress")
OUT_JS = os.path.join(OUT_DIR, "game.stress.js")
# The stress page lives at the project ROOT: game.js resolves its sprite
# paths relative to the page, so serving it from /stress/ 404s them all.
OUT_HTML = os.path.join(ROOT, "index.stress.html")
HARNESS = os.path.join(HERE, "stress_harness.js")


def build():
    src = open(SRC).read()
    original = src

    # 1. sleep -> yield only
    src, n1 = re.subn(
        r"const sleep = \(ms\) => new Promise\(\(r\) => setTimeout\(r, ms\)\);",
        "const sleep = (_ms) => new Promise((r) => setTimeout(r, 0));",
        src)
    if n1 != 1:
        raise SystemExit("sleep() line not found or not unique — update this script")

    # 2. animation durations -> 0
    src, n2 = re.subn(r"hopMs: 150,", "hopMs: 0,", src)
    src, n3 = re.subn(r"glideTotalMs: 820,", "glideTotalMs: 0,", src)
    if n2 != 1 or n3 != 1:
        raise SystemExit("TUNING duration lines not found or not unique")

    # 3. game-transition timers
    src, n4 = re.subn(r"\}, 1500\);", "}, 40);", src)
    src, n5 = re.subn(r"resolve\(\); \}, 1600\);", "resolve(); }, 40);", src)
    if n4 != 1 or n5 != 1:
        raise SystemExit("transition timer lines not found or not unique")

    harness = open(HARNESS).read()
    out = src + "\n\n" + harness

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JS, "w") as fh:
        fh.write(out)

    # diff must be exactly the two substitutions
    body = out[:out.index(harness)]
    expected = original
    expected = expected.replace(
        "const sleep = (ms) => new Promise((r) => setTimeout(r, ms));",
        "const sleep = (_ms) => new Promise((r) => setTimeout(r, 0));")
    expected = expected.replace("hopMs: 150,", "hopMs: 0,")
    expected = expected.replace("glideTotalMs: 820,", "glideTotalMs: 0,")
    expected = expected.replace("}, 1500);", "}, 40);")
    expected = expected.replace("resolve(); }, 1600);", "resolve(); }, 40);")
    if body.rstrip("\n") != expected.rstrip("\n"):
        raise SystemExit("stress variant drifted beyond the 3 sanctioned edits")

    html = open(os.path.join(ROOT, "index.html")).read()
    # only the script src changes; asset paths stay relative to the root page
    STAMP = str(int(os.path.getmtime(SRC)))
    html = html.replace('src="src/game.js"',
        f'src="stress/game.stress.js?v={STAMP}"')
    with open(OUT_HTML, "w") as fh:
        fh.write(html)

    print(f"wrote {OUT_JS}")
    print(f"wrote {OUT_HTML}")
    print("diff vs production: exactly 5 sanctioned timing edits — OK")


if __name__ == "__main__":
    build()
