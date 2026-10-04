#!/usr/bin/env python3
"""
make_release.py — produce the deployable, self-contained release folder.

The point of this step is that nothing in the result depends on this machine:
no dev server, no absolute paths, no logs, no PIDs, no /tmp references. Every
asset path stays relative so the same folder works from a domain root, a
subdirectory (GitHub project pages live at /<repo>/), a USB stick, or file://.

It also VERIFIES that the game assets are copied byte-for-byte, so "looks exactly
the same after upload" is a checked claim rather than an assumption.
"""

import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(os.path.dirname(ROOT), "snake-ladder-game")

# runtime assets the page actually requests
RUNTIME_ASSETS = [
    "assets/final/snake.png",
    "assets/final/snake_head.png",
    "assets/final/snake_skin.png",
    "assets/final/avatars/avatar_p1.png",
    "assets/final/avatars/avatar_p2.png",
    "assets/final/avatars/avatar_p3.png",
    "assets/final/avatars/avatar_p4.png",
    "assets/final/avatars/die_1.png",
    "assets/final/avatars/die_2.png",
    "assets/final/avatars/die_3.png",
    "assets/final/avatars/die_4.png",
    "assets/final/avatars/die_5.png",
    "assets/final/avatars/die_6.png",
]
ICONS = [f"assets/final/favicon-{n}.png" for n in (32, 64, 180, 192)] + \
        ["assets/final/icon-512.png"]
META = ["assets/final/snake_assets.json", "assets/final/snake.json"]
# sources kept for regeneration (FLUX.2 swap, retuning) — not fetched at runtime
SOURCES = ["assets/raw/snake_A.jpg", "assets/raw/snake_B.jpg", "assets/raw/snake_C.jpg",
           "assets/final/avatars/die_face.jpg", "assets/final/avatars/die_shell.jpg",
           "assets/final/avatars/avatar_p1.jpg", "assets/final/avatars/avatar_p2.jpg",
           "assets/final/avatars/avatar_p3.jpg", "assets/final/avatars/avatar_p4.jpg"]
CODE = ["index.html", "src/game.js", "src/style.css"]
TOOLS = ["tools/make_sprite.py", "tools/extract_parts.py", "tools/make_ui_assets.py",
         "tools/preview.py", "tools/gen_flux2.py", "tools/make_stress.py",
         "tools/stress_harness.js", "tools/make_release.py",
         "tools/build_single_file.py", "tools/RELEASE-README.md"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    # Build the single-file bundle FIRST: the release folder is wiped below, and
    # one command should produce the whole deployable output.
    import subprocess
    print("building single-file bundle ...")
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_single_file.py")],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit("single-file build failed")

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    problems = []
    single = os.path.join(ROOT, "dist", "snake-ladder.html")
    if os.path.exists(single):
        os.makedirs(os.path.join(OUT, "dist"), exist_ok=True)
        shutil.copy2(single, os.path.join(OUT, "dist", "snake-ladder.html"))

    for rel in CODE + RUNTIME_ASSETS + ICONS + META + SOURCES + TOOLS:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            problems.append(f"missing source: {rel}")
            continue
        dst = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    # .gitignore ships; the long dev README is kept with the tools instead,
    # and the release gets its own deployment-first README (written separately).
    shutil.copy2(os.path.join(ROOT, ".gitignore"), os.path.join(OUT, ".gitignore"))
    shutil.copy2(os.path.join(ROOT, "README.md"),
                 os.path.join(OUT, "tools", "DEV-NOTES.md"))
    # deployment-first README, authored in tools/ so one command rebuilds all
    shutil.copy2(os.path.join(ROOT, "tools", "RELEASE-README.md"),
                 os.path.join(OUT, "README.md"))

    # ---- verification ----------------------------------------------------
    print("verifying copied assets are byte-identical ...")
    bad = 0
    for rel in RUNTIME_ASSETS + ICONS:
        a, b = os.path.join(ROOT, rel), os.path.join(OUT, rel)
        if not os.path.exists(b) or sha(a) != sha(b):
            print(f"  MISMATCH {rel}")
            bad += 1
    print(f"  {len(RUNTIME_ASSETS) + len(ICONS)} assets checked, {bad} mismatches")

    # ---- no machine-specific leftovers -----------------------------------
    print("scanning for machine-specific references ...")
    needles = [b"/Users/", b"127.0.0.1", b"localhost:", b"/tmp/", b"file:///",
               b"devserver"]
    # Known-good: the localhost gate in the error reporter, docs that tell you how
    # to start a local server, and .gitignore naming the dev artefacts it excludes.
    needles_all = tuple(needles)
    allow = {
        ("src/game.js", b"127.0.0.1"),           # reportError() beacons only on localhost
        ("dist/snake-ladder.html", b"127.0.0.1"),  # same gate, inlined into the bundle
        ("tools/DEV-NOTES.md", b"127.0.0.1"),     # documented local dev command
        ("README.md", b"localhost:"),            # "open http://localhost:8000" in the run steps
        ("tools/RELEASE-README.md", b"localhost:"),
        (".gitignore", b"devserver"),             # the file whose job is to exclude it
    }
    # the scanner itself necessarily contains every needle it searches for
    allow |= {("tools/make_release.py", n) for n in needles_all}
    hits = []
    for dirpath, dirnames, filenames in os.walk(OUT):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if fn.endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            rel = os.path.relpath(p, OUT)
            with open(p, "rb") as fh:
                data = fh.read()
            for n in needles:
                if n in data and (rel, n) not in allow:
                    hits.append((rel, n.decode()))
    if hits:
        for p, n in hits:
            print(f"  FOUND {n!r} in {p}")
        problems.extend(f"machine-specific {n} in {p}" for p, n in hits)
    else:
        print("  clean — only the intentional localhost gate / docs / .gitignore")

    # ---- every path the page requests must exist -------------------------
    missing = []
    for rel in RUNTIME_ASSETS:
        if not os.path.exists(os.path.join(OUT, rel)):
            missing.append(rel)
    if missing:
        problems.extend("not in release: " + m for m in missing)

    total = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fs in os.walk(OUT) for f in fs
    )
    print(f"\nrelease: {OUT}")
    print(f"size   : {total/1e6:.1f} MB")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("OK — release is self-contained")


if __name__ == "__main__":
    main()
