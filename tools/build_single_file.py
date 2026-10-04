#!/usr/bin/env python3
"""
build_single_file.py — inline the entire game into ONE .html file.

Why: the user wants to verify on a phone *before* hosting anything. A single file
can be AirDropped, emailed, or dropped onto any static host and opened with zero
folders and no server.

Assets are embedded verbatim as base64 data URIs — no resizing, no re-encoding —
so it looks byte-for-byte identical to the folder build.

Design note: every asset path is rewritten to go through a single inlined
__ASSET_MAP__ lookup rather than being substituted one-by-one. Substituting
literals is what broke dice_2..6 previously: `die_${n}.png` is ONE template
literal shared by every n, so a naive per-n replace clobbers it with the first
match and silently drops the rest. A manifest resolves it correctly for any n.
"""

import base64
import json
import mimetypes
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "dist", "snake-ladder.html")

# dynamic path in game.js, kept as an explicit (path -> JS expression) rule
DYNAMIC = {
    "assets/final/avatars/die_${n}.png":
        '__ASSET_MAP__["assets/final/avatars/die_" + n + ".png"]',
}
# The dynamic lookup builds a key at runtime, so those concrete files must be
# present in the manifest or the die will 404 inside the single-file build.
DYNAMIC_FILES = [f"assets/final/avatars/die_{n}.png" for n in range(1, 7)]


def data_uri(rel):
    p = os.path.join(ROOT, rel)
    mime = mimetypes.guess_type(p)[0] or "application/octet-stream"
    with open(p, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()


def main():
    html = open(os.path.join(ROOT, "index.html")).read()
    css = open(os.path.join(ROOT, "src", "style.css")).read()
    js = open(os.path.join(ROOT, "src", "game.js")).read()

    # 1. collect every asset the page or the script refers to
    paths = set(re.findall(r'(?:href|src)="(assets/[^"]+)"', html))
    paths |= set(re.findall(r"['\"](assets/[^'\"`\n]+)['\"]", js))
    # dynamic templates are built at runtime from n; they are not literal files
    # and must not be existence-checked or given a manifest entry.
    paths = {p for p in paths if not p.startswith("data:") and p not in DYNAMIC}
    paths |= set(DYNAMIC_FILES)
    missing = [p for p in paths if not os.path.exists(os.path.join(ROOT, p))]
    if missing:
        raise SystemExit("missing assets: " + ", ".join(sorted(missing)))

    # 2. build the manifest
    table = {p: data_uri(p) for p in sorted(paths)}
    manifest = "const __ASSET_MAP__ = {\n" + ",\n".join(
        f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in table.items()) + "\n};\n"

    # 3. rewrite the script: static literals and the dynamic template both go
    #    through the manifest
    for p in sorted(paths, key=len, reverse=True):
        if p in DYNAMIC:
            continue
        # ONE pass for both quote styles. Replacing 'p' first would emit
        # __ASSET_MAP__["p"], and the subsequent "p" pass would then match that
        # very key and wrap it again -> __ASSET_MAP__[__ASSET_MAP__["p"]]
        # which evaluates to undefined and makes the image fail to load.
        js = re.sub(r"""(['"])""" + re.escape(p) + r"""\1""",
                    lambda _m: "__ASSET_MAP__[" + json.dumps(p) + "]", js)
    for tmpl, expr in DYNAMIC.items():
        js = js.replace(f"`{tmpl}`", expr)

    # 4. rewrite html attributes
    def repl_attr(m):
        attr, p = m.group(1), m.group(2)
        # A data URI contains no quote characters, so the attribute stays
        # well-formed. Injecting a __ASSET_MAP__["..."] expression here would
        # terminate the attribute early and produce malformed HTML.
        return f'{attr}="{table[p]}"' if p in table else m.group(0)
    html = re.sub(r'(href|src)="(assets/[^"]+)"', repl_attr, html)

    # 5. inline css + js (+ manifest) and resolve the map in JS
    html = html.replace('<link rel="stylesheet" href="src/style.css" />',
                        "<style>\n" + css + "\n</style>")
    html = html.replace('<script src="src/game.js"></script>',
                        "<script>\n" + manifest + js + "\n</script>")

    # 6. verify: no asset path may survive as a live reference.
    #    Legitimate occurrences are (a) manifest keys inside the object literal,
    #    (b) __ASSET_MAP__[...] lookups, (c) data URIs. Strip all three, then
    #    anything still naming an assets/ path is a genuine miss.
    probe = html
    probe = re.sub(r'const __ASSET_MAP__ = \{.*?\n\};', '', probe, flags=re.S)
    probe = re.sub(r'__ASSET_MAP__\[[^\]]*\]', '', probe)
    probe = re.sub(r'data:image/[a-z]+;base64,[A-Za-z0-9+/=]+', '', probe)
    leftover = sorted(set(re.findall(r"['\"](assets/[^'\"`\n]{3,})['\"]", probe)))
    if leftover:
        raise SystemExit("unresolved asset paths: " + ", ".join(leftover))
    # guard against a lookup being wrapped twice (evaluates to undefined)
    if "__ASSET_MAP__[__ASSET_MAP__" in html:
        raise SystemExit("double-wrapped manifest lookup detected")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        fh.write(html)

    # 7. verify by fingerprint: each asset's own base64 must be present
    body = open(OUT).read()
    bad = []
    for rel, uri in table.items():
        if base64.b64encode(open(os.path.join(ROOT, rel), "rb").read()).decode()[:120] \
                not in body:
            bad.append(rel)
    print(f"wrote {OUT}  ({os.path.getsize(OUT)/1e6:.1f} MB)")
    print(f"assets inlined: {len(table) - len(bad)}/{len(table)}")
    if bad:
        print("NOT INLINED: " + ", ".join(bad))
        sys.exit(1)
    print("all assets verified by base64 fingerprint — visuals are unchanged")
    print("open it directly, or AirDrop it to a phone and open in any browser.")


if __name__ == "__main__":
    main()
