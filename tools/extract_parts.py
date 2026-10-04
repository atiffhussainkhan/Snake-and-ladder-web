#!/usr/bin/env python3
"""
extract_parts.py — split the transparent snake sprite into the two pieces a
Snake & Ladder board actually needs, and measure the anchors for each.

  snake_head.png  the photoreal head + a short neck, edge-feathered so it melts
                  into the body tube instead of showing a cut seam
  snake_skin.png  an opaque slab of belly/side scales, used as the repeating
                  fill pattern along the body

Why split instead of placing one photo: a coiled snake sprite has a fixed
aspect ratio. Squeezing it to span 2 squares makes it obese; spanning 9 squares
makes it paper-thin. Driving geometry procedurally and texturing it with the real
skin keeps every snake a believable thickness at any distance.

Outputs snake_assets.json describing both anchor points so game.js never has to
guess a pixel offset.
"""

import json
import os
import math
import sys

from PIL import Image, ImageFilter, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FINAL = os.path.join(ROOT, "assets", "final")


def alpha_centroid(alpha: Image.Image, x0: int, x1: int):
    """Alpha-weighted centroid of the region [x0,x1) — used to place anchors."""
    band = alpha.crop((x0, 0, x1, alpha.size[1]))
    px = band.load()
    w, h = band.size
    sx = sy = sw = 0.0
    for y in range(h):
        for x in range(w):
            a = px[x, y]
            if a:
                sx += x * a
                sy += y * a
                sw += a
    if sw == 0:
        return (x0, alpha.size[1] // 2)
    return (x0 + sx / sw, sy / sw)


def rightmost_mass(alpha: Image.Image):
    """The right edge of the neck, so the body tube can start exactly there."""
    w, h = alpha.size
    px = alpha.load()
    for x in range(w - 1, -1, -1):
        for y in range(h):
            if px[x, y] > 200:
                return (x, y)
    return (w - 1, h // 2)


def main():
    sprite_path = os.path.join(FINAL, "snake.png")
    if not os.path.exists(sprite_path):
        raise SystemExit("run make_sprite.py first")
    sp = Image.open(sprite_path).convert("RGBA")
    W, H = sp.size
    alpha = sp.split()[3]
    meta = json.load(open(os.path.join(FINAL, "snake.json")))
    hx, hy = meta["head"]
    tx, ty = meta["tail"]

    # ---- head plate: snout to just past the neck -------------------------
    # Crop TIGHTLY around the head band only. A full-height crop would swallow
    # the upper loop of the coil and the neck anchor would land on the wrong body.
    hy_px = int(hy)
    head_x0, head_y0 = 0, max(0, hy_px - 250)
    head_x1 = min(W, int(hx) + 590)
    head = sp.crop((head_x0, head_y0, head_x1, H))
    hw, hh = head.size
    ha = head.split()[3]

    # Fade the right (neck) side out so the head melts into the body tube
    # instead of showing a hard cut seam.
    ramp = Image.new("L", (hw, 1))
    fade_from = int(hw * 0.52)
    for x in range(hw):
        if x < fade_from:
            v = 255
        else:
            t = (x - fade_from) / float(max(1, hw - fade_from))
            v = int(255 * (1.0 - t) ** 1.35)
        ramp.putpixel((x, 0), max(0, min(255, v)))
    ha = ImageChops.multiply(ha.filter(ImageFilter.GaussianBlur(1.1)),
                             ramp.resize((hw, hh)))
    head = head.copy()
    head.putalpha(ha)
    head.save(os.path.join(FINAL, "snake_head.png"), "PNG", optimize=True)

    # ---- skin plate: opaque scale texture -------------------------------
    sx0 = int(min(W, max(0, (hx + tx) * 0.42)))
    sy0 = int(max(0, min(H - 330, hy - 165)))
    skin = sp.crop((sx0, sy0, min(W, sx0 + 620), min(H, sy0 + 330)))
    skin = skin.copy()
    skin.putalpha(Image.new("L", skin.size, 255))
    skin.save(os.path.join(FINAL, "snake_skin.png"), "PNG", optimize=True)

    # ---- anchors (all relative to the head plate) -----------------------
    face_local = alpha_centroid(ha, 0, int(hw * 0.45))
    neck_local = alpha_centroid(ha, int(hw * 0.88), hw)

    # The nose points away from the neck.
    facing = math.degrees(math.atan2(face_local[1] - neck_local[1],
                                      face_local[0] - neck_local[0]))
    # Quantise to a tidy cardinal: the source head is a clean 3/4 profile.
    facing = round(facing / 15.0) * 15.0

    assets = {
        "head_png": "assets/final/snake_head.png",
        "skin_png": "assets/final/snake_skin.png",
        "sprite_png": "assets/final/snake.png",
        "head": {
            "width": hw,
            "height": hh,
            # Where the FACE sits inside the head plate -> the bite square.
            "face": [round(face_local[0], 2), round(face_local[1], 2)],
            # Where the neck leaves the plate -> where the body tube begins.
            "neck": [round(neck_local[0], 2), round(neck_local[1], 2)],
            # Degrees, canvas convention (y down). Nose points along this.
            "facing_deg": round(facing, 2),
        },
        "skin": {"width": skin.size[0], "height": skin.size[1]},
        "sprite": meta,
    }
    out = os.path.join(FINAL, "snake_assets.json")
    with open(out, "w") as fh:
        json.dump(assets, fh, indent=2)

    print(f"head  {hw}x{hh}  face=({face_local[0]:.0f},{face_local[1]:.0f}) "
          f"neck=({neck_local[0]:.0f},{neck_local[1]:.0f}) facing={facing:.0f}deg")
    print(f"skin  {skin.size[0]}x{skin.size[1]}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
