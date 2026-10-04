#!/usr/bin/env python3
"""
make_ui_assets.py — turn the generated portraits and the blank die face into
game-ready UI assets.

Avatars
    Circular RGBA cut-outs, framed on the face. The generated portraits are
    already centred head-and-shoulders, so a circle crop works directly.

Dice
    Six faces built from ONE photoreal blank die face with the pips drawn
    programmatically. This is deliberate: a generated "dice showing 4 pips"
    cannot be trusted to show exactly 4 pips, and a board game whose die lies
    about its roll is broken. The die body is the AI image; only the pips are
    drawn, so every face is exact by construction.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AV = os.path.join(ROOT, "assets", "final", "avatars")

AVATAR_SIZE = 320
DIE_SIZE = 256

# pip layout in normalised face coordinates
PIPS = {
    1: [(0.50, 0.50)],
    2: [(0.28, 0.28), (0.72, 0.72)],
    3: [(0.27, 0.27), (0.50, 0.50), (0.73, 0.73)],
    4: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.72), (0.72, 0.72)],
    5: [(0.27, 0.27), (0.73, 0.27), (0.50, 0.50), (0.27, 0.73), (0.73, 0.73)],
    6: [(0.28, 0.27), (0.72, 0.27), (0.28, 0.50), (0.72, 0.50),
        (0.28, 0.73), (0.72, 0.73)],
}


def make_avatars():
    for i in range(1, 5):
        src = os.path.join(AV, f"avatar_p{i}.jpg")
        im = Image.open(src).convert("RGB")
        W, H = im.size
        # frame the face: sit the circle centre a little above the middle
        cx, cy, r = W * 0.5, H * 0.47, W * 0.44
        box = (int(cx - r), int(cy - r), int(cx + r), int(cy + r))
        face = im.crop(box).resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

        # circular alpha with a 1.5px feather
        s = AVATAR_SIZE
        mask = Image.new("L", (s * 4, s * 4), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, s * 4 - 1, s * 4 - 1], fill=255)
        mask = mask.resize((s, s), Image.LANCZOS).filter(
            ImageFilter.GaussianBlur(0.6))

        out = face.convert("RGBA")
        out.putalpha(mask)
        out.save(os.path.join(AV, f"avatar_p{i}.png"), "PNG", optimize=True)
        print(f"avatar_p{i}.png  {out.size}")


def _pip(d, cx, cy, r):
    """One recessed pip: dark centre, lighter lip, soft edge."""
    # body
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(38, 33, 28, 255))
    # concave highlight along the lower lip
    d.arc([cx - r * 0.86, cy - r * 0.86, cx + r * 0.86, cy + r * 0.86],
          start=25, end=155, fill=(122, 112, 94, 190), width=max(2, int(r * 0.30)))


def make_dice():
    src = Image.open(os.path.join(AV, "die_face.jpg")).convert("RGB")
    g = src.convert("L")
    bbox = g.point(lambda p: 255 if p > 105 else 0).getbbox()
    if not bbox:
        raise SystemExit("could not locate the die in die_face.jpg")
    die = src.crop(bbox)

    s = DIE_SIZE
    die = die.resize((s, s), Image.LANCZOS)

    # rounded-corner alpha so the black backdrop is gone
    mask = Image.new("L", (s * 4, s * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, s * 4 - 1, s * 4 - 1], radius=int(s * 4 * 0.17), fill=255)
    mask = mask.resize((s, s), Image.LANCZOS)
    # knock out anything still near-black (residual backdrop)
    lum = die.convert("L")
    mask = Image.composite(mask, Image.new("L", (s, s), 0),
                           lum.point(lambda p: 255 if p > 42 else 0))
    mask = mask.filter(ImageFilter.GaussianBlur(0.7))

    pr = s * 0.082                      # pip radius
    for n, pts in PIPS.items():
        face = die.copy().convert("RGBA")
        layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for (fx, fy) in pts:
            _pip(d, fx * s, fy * s, pr)
        layer = layer.filter(ImageFilter.GaussianBlur(0.9))
        face.alpha_composite(layer)
        face.putalpha(mask)
        out = os.path.join(AV, f"die_{n}.png")
        face.save(out, "PNG", optimize=True)
        print(f"die_{n}.png  pips={n}  {face.size}")


if __name__ == "__main__":
    os.makedirs(AV, exist_ok=True)
    make_avatars()
    make_dice()
    print("done")
