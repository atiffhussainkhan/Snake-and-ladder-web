#!/usr/bin/env python3
"""
make_sprite.py — turn a generated snake photo into a game-ready transparent sprite
with automatically-measured HEAD and TAIL anchor points.

Why this exists
---------------
A Snake & Ladder board needs the snake's head to sit exactly on the "bite" square
and its tail exactly on the "landing" square. That means the asset must carry
machine-readable anchor metadata, not just pixels. This script:

  1. Builds a soft alpha matte from the pure-white studio background (C-speed PIL LUTs).
  2. Suppresses the cast shadow and the white fringe (decontamination).
  3. Trims to the subject bounding box.
  4. Finds the principal axis of the coil via PCA over the mask.
  5. Locates the two endpoints of that axis and measures which end is THICKER.
  6. The thicker end is the HEAD (a snake tapers to a point at the tail).
  7. Emits a sidecar JSON with head/tail anchors, axis angle, span and thickness.

Usage:
    python3 make_sprite.py <input.jpg> <output.png> <output.json>
"""

import json
import math
import sys

from PIL import Image, ImageFilter

# --- Matte tuning -----------------------------------------------------------
# The generated sources are shot on a seamless white sweep. These two numbers are
# the luminance band mapped to fully-transparent -> fully-opaque.
WHITE_LEVEL = 246.0   # >= this luminance  => background
DARK_LEVEL = 62.0     # <= this luminance  => solid snake
# Levels pass afterwards to burn off the soft grey shadow and the light halo that
# the white backdrop bleeds into the scale edges.
SHADOW_FLOOR = 30.0
SHADOW_CEIL = 172.0

# Morphology applied to the alpha channel only.
ERODE_RADIUS = 1      # px, kills the 1px contaminated edge ring
FEATHER_RADIUS = 0.7  # px, restores a 1px antialiased edge


def build_alpha(gray: Image.Image) -> Image.Image:
    """Luminance -> alpha via a 256-entry lookup table (runs in C inside PIL)."""

    span = WHITE_LEVEL - DARK_LEVEL

    def raw(lum: int) -> int:
        a = (WHITE_LEVEL - lum) / span
        a = 0.0 if a < 0.0 else (1.0 if a > 1.0 else a)
        return int(a * 255.0 + 0.5)

    alpha = gray.point([raw(i) for i in range(256)])

    # Second LUT: suppress residual shadow haze + residual white halo.
    def levels(a: int) -> int:
        t = (a - SHADOW_FLOOR) / (SHADOW_CEIL - SHADOW_FLOOR)
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        return int(t * 255.0 + 0.5)

    return alpha.point([levels(i) for i in range(256)])


def clean_alpha(alpha: Image.Image) -> Image.Image:
    """Erode to shed the white fringe, then feather back to an antialiased edge."""
    if ERODE_RADIUS >= 1:
        alpha = alpha.filter(ImageFilter.MinFilter(ERODE_RADIUS * 2 + 1))
    if FEATHER_RADIUS > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(FEATHER_RADIUS))
    return alpha


def unmatte(rgb: Image.Image, alpha: Image.Image, buckets: int = 16) -> Image.Image:
    """Undo white-backdrop spill using the compositing equation.

    A pixel of a subject composited over pure white obeys

        observed = subject * a  +  255 * (1 - a)

    so the true colour is

        subject = 255 + (observed - 255) / a

    Without this step the white sweep bleeds into every scale edge and leaves a
    pale halo. Alpha is quantised into buckets and each bucket gets its own
    per-channel lookup table, which keeps the whole thing inside PIL's C loops.
    """
    step = max(1, 256 // buckets)
    out_bands = []
    for band in rgb.split():
        acc = Image.new("L", rgb.size, 0)
        for k in range(1, buckets + 1):
            lo = (k - 1) * step
            hi = k * step if k < buckets else 256
            av = hi / 255.0
            m = alpha.point(lambda p, lo=lo, hi=hi: 255 if lo <= p < hi else 0)
            if m.getbbox() is None:
                continue
            lut = [max(0, min(255, int(255.0 + (c - 255.0) / av + 0.5))) for c in range(256)]
            acc.paste(band.point(lut), (0, 0), m)
        out_bands.append(acc)
    return Image.merge("RGB", out_bands)


def drop_specks(mask: Image.Image, min_area: int) -> Image.Image:
    """Remove tiny disconnected blobs left behind by JPEG noise."""
    px = mask.load()
    w, h = mask.size
    seen = bytearray(w * h)
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not px[x, y] or seen[i]:
                continue
            stack = [(x, y)]
            seen[i] = 1
            blob = []
            while stack:
                cx, cy = stack.pop()
                blob.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        j = ny * w + nx
                        if px[nx, ny] and not seen[j]:
                            seen[j] = 1
                            stack.append((nx, ny))
            if len(blob) >= min_area:
                for bx, by in blob:
                    out[by * w + bx] = 255
    res = Image.new("L", mask.size, 0)
    res.putdata(bytes(out))
    return res


def analyse(alpha: Image.Image, work: int = 512):
    """PCA the mask to find the coil's principal axis, then its two endpoints."""
    w, h = alpha.size
    scale = work / float(w)
    sw, sh = max(8, int(w * scale)), max(8, int(h * scale))
    small = alpha.resize((sw, sh), Image.BILINEAR).point(lambda p: 255 if p > 128 else 0)
    spx = small.load()

    pts = [(x, y) for y in range(sh) for x in range(sw) if spx[x, y]]
    if len(pts) < 50:
        raise SystemExit("mask too small — check the matte thresholds")

    n = float(len(pts))
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = syy = sxy = 0.0
    for x, y in pts:
        dx, dy = x - mx, y - my
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    sxx /= n
    syy /= n
    sxy /= n

    # Principal eigenvector of the symmetric 2x2 covariance.
    tr = sxx + syy
    det = sxx * syy - sxy * sxy
    disc = max(0.0, (tr * tr / 4.0) - det)
    lam = tr / 2.0 + math.sqrt(disc)
    ux, uy = lam - syy, sxy
    if abs(ux) < 1e-9 and abs(uy) < 1e-9:
        ux, uy = 1.0, 0.0
    ulen = math.hypot(ux, uy)
    ux, uy = ux / ulen, uy / ulen
    vx, vy = -uy, ux

    proj = [((x - mx) * ux + (y - my) * uy, (x - mx) * vx + (y - my) * vy) for x, y in pts]
    pmin = min(p[0] for p in proj)
    pmax = max(p[0] for p in proj)
    span = pmax - pmin
    if span <= 0:
        raise SystemExit("degenerate axis")

    # Endpoint anchors: centroid of the mass within 12% of each extreme, so the
    # anchor sits in the middle of the head / tail blob rather than on a stray tip.
    band = span * 0.12

    def end_stats(edge: str):
        sel = []
        for (p, q), (x, y) in zip(proj, pts):
            near_min = p <= pmin + band
            if (edge == "min" and near_min) or (edge == "max" and p >= pmax - band):
                sel.append((q, x, y))
        if not sel:
            return (mx, my), 0.0
        cx = sum(s[1] for s in sel) / len(sel)
        cy = sum(s[2] for s in sel) / len(sel)
        # Perpendicular spread = how chunky this end is. Head >> tail.
        thick = max(s[0] for s in sel) - min(s[0] for s in sel)
        return (cx, cy), thick

    (ax, ay), th_a = end_stats("min")
    (bx, by), th_b = end_stats("max")

    # A real snake tapers to a point: the THICKER end is the head.
    if th_b > th_a:
        head_s, tail_s = (bx, by), (ax, ay)
        head_th, tail_th = th_b, th_a
    else:
        head_s, tail_s = (ax, ay), (bx, by)
        head_th, tail_th = th_a, th_b

    # Overall perpendicular thickness of the whole coil.
    all_q = [p[1] for p in proj]
    body_thick = max(all_q) - min(all_q)

    back = 1.0 / scale
    hx, hy = head_s[0] * back, head_s[1] * back
    tx, ty = tail_s[0] * back, tail_s[1] * back
    axis_angle = math.degrees(math.atan2(ty - hy, tx - hx))

    return {
        "head": [round(hx, 2), round(hy, 2)],
        "tail": [round(tx, 2), round(ty, 2)],
        "head_thickness_px": round(head_th * back, 1),
        "tail_thickness_px": round(tail_th * back, 1),
        "body_thickness_px": round(body_thick * back, 1),
        "head_tail_span_px": round(math.hypot(tx - hx, ty - hy), 1),
        "axis_angle_deg": round(axis_angle, 2),
        "mask_pixels": len(pts),
    }


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    src, out_png, out_json = sys.argv[1:4]

    im = Image.open(src).convert("RGB")
    gray = im.convert("L")

    alpha = build_alpha(gray)
    hard = alpha.point(lambda p: 255 if p > 128 else 0)
    hard = drop_specks(hard, min_area=(im.size[0] * im.size[1]) // 60000)

    # Rebuild the matte as binary, then feather — keeps edges soft but stops
    # background haze bleeding back in.
    alpha = hard.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    alpha = clean_alpha(alpha)

    bbox = alpha.getbbox()
    if not bbox:
        raise SystemExit("empty mask")
    alpha = alpha.crop(bbox)
    rgb = im.crop(bbox)
    # Reclaim the colour the white backdrop borrowed from every soft edge.
    rgb = unmatte(rgb, alpha)
    w, h = alpha.size

    meta = analyse(alpha)
    meta.update({"src": src, "width": w, "height": h,
                 "bbox": list(bbox), "trimmed_size": [w, h]})

    sprite = Image.merge("RGBA", (*rgb.split(), alpha))
    sprite.save(out_png, "PNG", optimize=True)
    with open(out_json, "w") as fh:
        json.dump(meta, fh, indent=2)

    print(f"wrote {out_png}  {w}x{h}")
    print(f"  head  {meta['head']}   thickness {meta['head_thickness_px']}px")
    print(f"  tail  {meta['tail']}   thickness {meta['tail_thickness_px']}px")
    print(f"  span  {meta['head_tail_span_px']}px  angle {meta['axis_angle_deg']}deg")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
