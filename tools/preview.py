#!/usr/bin/env python3
"""
preview.py — render the board exactly the way src/game.js does, and prove the
anchors land where they are supposed to.

The maths here is a deliberate mirror of game.js (squareToCell / centreOf /
serpentine / frame / head transform). If the two ever drift apart the preview
would lie, so treat this as the reference implementation of the geometry.

Outputs
    assets/final/preview_board.png     the board as the player sees it
    assets/final/preview_anchors.png   same, with head/tail anchors called out
    assets/final/preview_zoom.png      close-up of individual snakes
"""

import json
import math
import os

from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FINAL = os.path.join(ROOT, "assets", "final")

# ---- board config (mirror of game.js) ------------------------------------
GRID, CELLS, PAD, CSSv = 10, 100, 26, 1240
CELL = (CSSv - PAD * 2) / GRID
SNAKES = [(16, 6), (47, 26), (49, 11), (56, 53), (62, 19),
          (64, 60), (87, 24), (93, 73), (95, 75), (98, 78)]
# must mirror LADDERS in src/game.js — no start at 1, no end at 99/100,
# no start or end on a snake face
LADDERS = [(4, 14), (9, 31), (21, 42), (28, 84),
           (36, 44), (51, 67), (71, 91), (80, 96)]

HEAD_LEN_FRAC, BODY_W_FRAC, WOBBLE_FRAC, WAVES, SAMPLES = 0.85, 0.32, 0.125, 1.7, 150

A = json.load(open(os.path.join(FINAL, "snake_assets.json")))
HEAD_PNG = Image.open(os.path.join(ROOT, A["head_png"])).convert("RGBA")
SKIN_PNG = Image.open(os.path.join(ROOT, A["skin_png"])).convert("RGBA")
FACE = tuple(A["head"]["face"])
NECK = tuple(A["head"]["neck"])
FACING = A["head"]["facing_deg"]


# ---- geometry -------------------------------------------------------------
def square_to_cell(n):
    i, row = n - 1, (n - 1) // GRID
    col = i % GRID
    if row % 2 == 1:
        col = GRID - 1 - col
    return col, row


def centre_of(n):
    col, row = square_to_cell(n)
    return (PAD + (col + 0.5) * CELL, PAD + (GRID - 1 - row + 0.5) * CELL)


def serpentine(A_, B_):
    dx, dy = B_[0] - A_[0], B_[1] - A_[1]
    D = math.hypot(dx, dy) or 1.0
    ux, uy = dx / D, dy / D
    vx, vy = -uy, ux
    amp = D * WOBBLE_FRAC
    pts = []
    for k in range(SAMPLES + 1):
        t = k / SAMPLES
        pin = math.sin(math.pi * t)
        off = math.sin(t * math.pi * WAVES) * amp * pin
        pts.append((A_[0] + dx * t + vx * off, A_[1] + dy * t + vy * off, t))
    return pts


def half_width(t, max_w):
    """Tube half-width: pointed at the tail, and ramped up out from under the head.

    The ramp matters — the head plate's neck exits slightly off-axis, so a body
    that started at full width at the bite square would step against it. Growing
    from ~42% keeps the start hidden behind the head, and the body is back to
    full width within about a third of a square.
    """
    taper = 0.5 + 0.5 * math.cos(math.pi * (t ** 1.5))
    ramp = min(1.0, 0.42 + t * 9.0)
    return max_w * taper * ramp


def ribbon_polygon(pts):
    left, right = [], []
    n = len(pts)
    for i, (x, y, t) in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        w = half_width(t, max_w)
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    right.reverse()
    return left + right


max_w = 0  # set per-snake in render_snake


# ---- tube shading ---------------------------------------------------------
def _blob(ref=64):
    """One pre-rendered lit sphere, reused for every tube cross-section."""
    im = Image.new("RGBA", (ref, ref), (0, 0, 0, 0))
    px = im.load()
    c, r = ref / 2.0, ref / 2.0 - 1.0
    lx, ly = c - r * 0.30, c - r * 0.34
    for y in range(ref):
        for x in range(ref):
            d = math.hypot(x - lx, y - ly) / (r * 1.42)
            t = min(1.0, d)
            t = t ** 0.85
            col = (int(132 * (1 - t) + 5 * t), int(146 * (1 - t) + 7 * t), int(170 * (1 - t) + 11 * t))
            a = 255 if t < 0.80 else int(255 * (1 - (t - 0.80) / 0.20))
            px[x, y] = (col[0], col[1], col[2], max(0, a))
    return im


BLOB = _blob()


def draw_tube(canvas_rgb, pts, poly):
    """Lit cross-sections give the round shading; a smooth polygon supplies the
    silhouette. Using the polygon (not the blob alpha) as the final mask is what
    removes the beading you get from stacking discrete circles."""
    lit = Image.new("RGBA", canvas_rgb.size, (0, 0, 0, 0))
    for x, y, t in pts:
        w = half_width(t, max_w)
        d = max(3, int(w * 2.1))
        lit.alpha_composite(BLOB.resize((d, d), Image.LANCZOS),
                            (int(x - d / 2), int(y - d / 2)))
    lit = lit.filter(ImageFilter.GaussianBlur(1.6))

    tile = Image.new("RGB", canvas_rgb.size, (0, 0, 0))
    step = 104
    scaled = SKIN_PNG.resize((step, step), Image.LANCZOS)
    for ty in range(0, canvas_rgb.size[1], step):
        for tx in range(0, canvas_rgb.size[0], step):
            tile.paste(scaled, (tx, ty))

    base = lit.convert("RGB")
    mixed = Image.blend(base, ImageChops.overlay(base, tile), 0.45)

    mask = Image.new("L", canvas_rgb.size, 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.7))

    out = mixed.convert("RGBA")
    out.putalpha(mask)
    canvas_rgb.alpha_composite(out)
    return out


def place_head(canvas_rgba, at, theta_deg, scale):
    """Place the head plate so its FACE anchor lands exactly on `at`, rotated so
    the nose points along `theta_deg` (canvas convention, y down).

    Built from resize + rotate because Image.transform() is broken in this
    Pillow build (even EXTENT returns an empty layer). Empirically, for a dot at
    (0,0) in a 100x100 image, rotate(90) sends it to (0,99), which gives
        M = [[cos t, sin t], [-sin t, cos t]]
    i.e. PIL rotate(t) is a canvas-convention rotation by -t.
    """
    w0, h0 = HEAD_PNG.size
    tw = max(1, int(round(w0 * scale)))
    th = max(1, int(round(h0 * scale)))
    img = HEAD_PNG.resize((tw, th), Image.LANCZOS)

    f0 = (FACE[0] * scale, FACE[1] * scale)
    c0 = (tw / 2.0, th / 2.0)

    ang = -theta_deg                      # PIL rotate is canvas-convention -t
    rot = img.rotate(ang, resample=Image.BICUBIC, expand=True)

    tr = math.radians(ang)
    c, s = math.cos(tr), math.sin(tr)
    c1 = (rot.size[0] / 2.0, rot.size[1] / 2.0)
    dx, dy = f0[0] - c0[0], f0[1] - c0[1]
    px = c1[0] + c * dx + s * dy
    py = c1[1] - s * dx + c * dy

    off = (int(round(at[0] - px)), int(round(at[1] - py)))
    canvas_rgba.alpha_composite(rot, off)


# ---- board ----------------------------------------------------------------
def font(sz, bold=True):
    cands = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


GAP, RAD = 4, 0.16


def shade_hex(hexstr, amt):
    n = int(hexstr[1:], 16)
    r, g, b = (n >> 16) & 255, (n >> 8) & 255, n & 255
    if amt > 0:
        r += (255 - r) * amt; g += (255 - g) * amt; b += (255 - b) * amt
    else:
        r *= 1 + amt; g *= 1 + amt; b *= 1 + amt
    c = lambda v: max(0, min(255, int(round(v))))
    return (c(r), c(g), c(b))


def _panel(im, box, fill, radius, bevel=True):
    """Rounded tile with a light top-left lip, dark bottom-right lip and gloss —
    the PIL mirror of the canvas bevel in paintBoard().

    Lips MIX toward white/black rather than adding channel values; adding
    saturates every tile to white and destroys the checkerboard.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    # No per-tile drop shadow here: with a 4px gutter the shadows from
    # neighbouring tiles overlap and fill the gap with solid black, which reads
    # as a harsh grid. The dark well between tiles already separates them.
    # body: vertical light->dark shading
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    for i in range(h):
        t = i / max(1, h - 1)
        amt = 0.09 - 0.17 * t
        bd.line([(0, i), (w, i)], fill=shade_hex(fill, amt) + (255,))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    im.paste(body, (x0, y0), mask)
    if not bevel:
        return

    px = im.load()
    lw = max(2, int(h * 0.035))
    for py in range(y0, y1):
        for pxx in range(x0, x1):
            dl = min(pxx - x0, py - y0)
            dr = min(x1 - 1 - pxx, y1 - 1 - py)
            if dl >= lw and dr >= lw:
                continue
            r, g, b, a = px[pxx, py]
            if dl < dr:                       # top-left lip -> mix toward white
                m = 0.40 * (1 - dl / lw)
                r += (255 - r) * m; g += (255 - g) * m; b += (255 - b) * m
            else:                              # bottom-right lip -> mix toward ink
                m = 0.30 * (1 - dr / lw)
                r += (14 - r) * m; g += (20 - g) * m; b += (32 - b) * m
            px[pxx, py] = (int(r), int(g), int(b), a)

    # Gentle gloss sweep. Must be alpha-composited, not pasted: paste() with an
    # RGBA source REPLACES the destination alpha, which was making every tile
    # semi-transparent and letting the dark well bleed through as a white wash.
    gl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gl)
    for i in range(h):
        t = i / max(1, h - 1)
        gd.line([(0, i), (w, i)], fill=(255, 255, 255, int(30 * max(0.0, 1 - t * 2.0))))
    gl.putalpha(ImageChops.multiply(gl.split()[3], mask))
    im.alpha_composite(gl, (x0, y0))


def paint_board():
    im = Image.new("RGBA", (CSSv, CSSv), (13, 17, 24, 255))
    d = ImageDraw.Draw(im, "RGBA")
    # outer slab
    d.rounded_rectangle([4, 4, CSSv - 4, CSSv - 4], radius=30, fill=(29, 36, 51, 255))
    d.rounded_rectangle([8, 8, CSSv - 8, CSSv - 8], radius=26,
                        outline=(120, 140, 175, 70), width=3)
    # recessed well
    well = PAD - 12
    d.rounded_rectangle([well, well, CSSv - well, CSSv - well], radius=20, fill=(12, 16, 23, 255))
    d.rounded_rectangle([well + 7, well + 7, CSSv - well - 7, CSSv - well - 7],
                        radius=16, outline=(0, 0, 0, 140), width=6)

    fn = font(int(CELL * 0.19))
    for n in range(1, CELLS + 1):
        col, row = square_to_cell(n)
        x = PAD + col * CELL
        y = PAD + (GRID - 1 - row) * CELL
        light = (row + col) % 2 == 0
        if n == CELLS:
            base = '#4a3a12'
        elif n == 1:
            base = '#0f4a5e'
        else:
            base = '#fbeed3' if light else '#bcd6f2'
        gx0, gy0 = x + GAP / 2, y + GAP / 2
        gx1, gy1 = gx0 + CELL - GAP, gy0 + CELL - GAP
        _panel(im, (int(gx0), int(gy0), int(gx1), int(gy1)), base, int((CELL - GAP) * RAD))
        d = ImageDraw.Draw(im, "RGBA")
        warm = n in (1, CELLS)
        tc = (255, 255, 255, 235) if warm else (44, 54, 74, 235)
        d.text((x + CELL / 2, y + CELL / 2 + 1.4), str(n), font=fn,
               fill=((0, 0, 0, 110) if warm else (255, 255, 255, 120)), anchor="mm")
        d.text((x + CELL / 2, y + CELL / 2), str(n), font=fn, fill=tc, anchor="mm")

    d = ImageDraw.Draw(im, "RGBA")
    fnc = font(int(CELL * 0.125), bold=True)
    d.text((PAD + 8, CSSv - PAD - CELL * 0.175 + 1.5), "START", font=fnc,
           fill=(0, 0, 0, 100), anchor="ls")
    d.text((PAD + 8, CSSv - PAD - CELL * 0.175), "START", font=fnc,
           fill=(120, 255, 190, 240), anchor="ls")
    d.text((CSSv - PAD - 8, PAD + CELL * 0.205 + 1.5), "FINISH", font=fnc,
           fill=(0, 0, 0, 100), anchor="rs")
    d.text((CSSv - PAD - 8, PAD + CELL * 0.205), "FINISH", font=fnc,
           fill=(255, 214, 120, 240), anchor="rs")
    return im


def draw_ladders(im):
    d = ImageDraw.Draw(im, "RGBA")
    for a, b in LADDERS:
        A_, B_ = centre_of(a), centre_of(b)
        dx, dy = B_[0] - A_[0], B_[1] - A_[1]
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        half = CELL * 0.17
        # Rail separation; rungs span exactly rail to rail.
        RAIL_GAP = CELL * 0.30
        for off in (0, -RAIL_GAP):
            d.line([(A_[0] + nx * (half + off), A_[1] + ny * (half + off)),
                    (B_[0] + nx * (half + off), B_[1] + ny * (half + off))],
                   fill=(138, 90, 43, 255), width=max(2, int(CELL * 0.055)))
            d.line([(A_[0] + nx * (half + off), A_[1] + ny * (half + off)),
                    (B_[0] + nx * (half + off), B_[1] + ny * (half + off))],
                   fill=(201, 139, 70, 255), width=max(1, int(CELL * 0.026)))
        steps = max(3, int(round(L / RAIL_GAP)))
        for k in range(1, steps):
            t = k / steps
            px_, py_ = A_[0] + dx * t, A_[1] + dy * t
            d.line([(px_ + nx * (half - RAIL_GAP), py_ + ny * (half - RAIL_GAP)),
                    (px_ + nx * half, py_ + ny * half)],
                   fill=(185, 124, 60, 255), width=max(1, int(CELL * 0.032)))


def render_snake(board, frm, to, mark=False):
    global max_w
    bite, land = centre_of(frm), centre_of(to)
    head_scale = (HEAD_LEN_FRAC * CELL) / HEAD_PNG.size[0]
    travel = math.atan2(land[1] - bite[1], land[0] - bite[0])

    # The body runs bite -> landing, so the tail lands exactly by construction.
    # It starts thin underneath the head (see half_width) rather than at the
    # head plate's neck anchor, which exits off-axis and would step against it.
    max_w = (BODY_W_FRAC * CELL) / 2.0
    pts = serpentine(bite, land)
    poly = ribbon_polygon(pts)

    # contact shadow
    sh = Image.new("RGBA", board.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon(
        [(x, y + CELL * 0.05) for x, y in poly], fill=(0, 0, 0, 130))
    board.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))

    tube = draw_tube(board, pts, poly)
    # rim
    edge = tube.split()[3].filter(ImageFilter.MaxFilter(5))
    rim = ImageChops.subtract(edge, tube.split()[3]).point(lambda p: int(p * 0.85))
    ink = Image.new("RGB", board.size, (4, 6, 10))
    board.alpha_composite(Image.merge("RGBA", (*ink.split(), rim)))

    # Nose leads: the plate's intrinsic facing is FACING, so the rotation that
    # points the nose away from the body (along travel + 180) is travel + 180 - FACING.
    place_head(board, bite, math.degrees(travel) + 180.0 - FACING, head_scale)

    if mark:
        d = ImageDraw.Draw(board, "RGBA")
        f = font(21)
        for (pt, col, lab) in ((bite, (255, 90, 90, 255), f"head {frm}"),
                               (land, (76, 194, 255, 255), f"tail {to}")):
            d.ellipse([pt[0] - 11, pt[1] - 11, pt[0] + 11, pt[1] + 11],
                      outline=col, width=4)
            d.line([pt[0] - 20, pt[1], pt[0] + 20, pt[1]], fill=col, width=2)
            d.line([pt[0], pt[1] - 20, pt[0], pt[1] + 20], fill=col, width=2)
            d.text((pt[0] + 15, pt[1] - 16), lab, font=f, fill=col)
    return board


def tile_base(n):
    col, row = square_to_cell(n)
    if n == CELLS:
        return (42, 36, 21)
    if n == 1:
        return (22, 48, 63)
    return (232, 226, 211) if (row + col) % 2 == 0 else (207, 214, 226)


def redraw_numbers(board):
    """Re-print the square numbers on top of the snakes with a board-coloured
    halo, so a snake crossing a square never makes it unreadable."""
    d = ImageDraw.Draw(board, "RGBA")
    fn = font(int(CELL * 0.19))
    for n in range(1, CELLS + 1):
        col, row = square_to_cell(n)
        x = PAD + col * CELL
        y = PAD + (GRID - 1 - row) * CELL
        warm = n in (1, CELLS)
        tc = (255, 255, 255, 230) if warm else (34, 42, 58, 215)
        d.text((x + CELL / 2, y + CELL / 2), str(n), font=fn, anchor="mm",
               fill=tc, stroke_width=3, stroke_fill=tile_base(n) + (235,))


def main():
    board = paint_board()
    draw_ladders(board)
    for frm, to in SNAKES:
        render_snake(board, frm, to)
    redraw_numbers(board)
    board.convert("RGB").save(os.path.join(FINAL, "preview_board.png"), "PNG")
    print("wrote preview_board.png")

    marked = paint_board()
    draw_ladders(marked)
    for frm, to in SNAKES:
        render_snake(marked, frm, to, mark=True)
    redraw_numbers(marked)
    marked.convert("RGB").save(os.path.join(FINAL, "preview_anchors.png"), "PNG")
    print("wrote preview_anchors.png")

    # close-ups: frame each snake by its own extent, clamped to the board
    picks = [(16, 6), (93, 73), (98, 78), (62, 19)]
    Z = 420
    strip = Image.new("RGB", (Z * len(picks), Z), (12, 15, 21))
    for i, (frm, to) in enumerate(picks):
        b = paint_board()
        draw_ladders(b)
        render_snake(b, frm, to, mark=True)
        redraw_numbers(b)
        p1, p2 = centre_of(frm), centre_of(to)
        half = max(abs(p1[0] - p2[0]), abs(p1[1] - p2[1])) / 2 + CELL * 1.9
        cx = min(max((p1[0] + p2[0]) / 2, half), CSSv - half)
        cy = min(max((p1[1] + p2[1]) / 2, half), CSSv - half)
        crop = b.convert("RGB").crop((int(cx - half), int(cy - half),
                                      int(cx + half), int(cy + half)))
        crop = crop.resize((Z, Z), Image.LANCZOS)
        strip.paste(crop, (i * Z, 0))
    strip.save(os.path.join(FINAL, "preview_zoom.png"), "PNG")
    print("wrote preview_zoom.png")

    # one big hero close-up
    hero = paint_board()
    draw_ladders(hero)
    render_snake(hero, 62, 19, mark=True)
    redraw_numbers(hero)
    p1, p2 = centre_of(62), centre_of(19)
    half = CELL * 4.4
    cx = min(max((p1[0] + p2[0]) / 2, half), CSSv - half)
    cy = min(max((p1[1] + p2[1]) / 2, half), CSSv - half)
    hero.convert("RGB").crop((int(cx - half), int(cy - half),
                              int(cx + half), int(cy + half))).resize(
        (1000, 1000), Image.LANCZOS).save(
        os.path.join(FINAL, "preview_hero.png"), "PNG")
    print("wrote preview_hero.png")


if __name__ == "__main__":
    main()
