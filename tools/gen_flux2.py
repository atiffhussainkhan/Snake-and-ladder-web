#!/usr/bin/env python3
"""
gen_flux2.py — regenerate the snake with genuine FLUX.2, then feed it through
the same asset pipeline the game already uses.

Why this exists
---------------
The snake currently in assets/ was produced by the image generator available in
this session, which does not expose a model selector. This script swaps in real
FLUX.2 from Black Forest Labs. Everything downstream is unchanged: the same
prompt shape, the same matte, the same PCA anchor measurement.

Requirements
    export BFL_API_KEY=...          # https://bfl.ai  ->  API keys
    python3 tools/gen_flux2.py

Endpoint shape (verified against docs.bfl.ai/flux_2/flux2_text_to_image)
    POST https://api.bfl.ai/v1/flux-2-pro-preview
         headers: x-key: $BFL_API_KEY, accept: application/json
         body:    {"prompt": ..., "width": ..., "height": ...}
    ->  {"id": ..., "polling_url": ...}
    GET  <polling_url>  ->  {"status": "Ready"|"Error"|"Failed"|..., "result": {"sample": "<url>"}}
    The sample URL is signed and expires ~10 minutes after Ready.

Pricing note: FLUX.2 [pro] bills from $0.03/megapixel of output, so a
2688x1344 image is ~3.6MP, roughly $0.11 per generation. [klein] 4B is ~10x
cheaper and is the better choice if you iterate on the look a lot.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "assets", "raw")

# Variants to sample. The first is the production base: head and tail are the
# two extreme ends of a clean horizontal axis, which is what makes the head->tail
# board anchoring exact.
PROMPTS = [
    ("snake_flux2_A", 2688, 1344,
     "Extreme photorealistic macro photograph of a single live black rat snake. "
     "Glossy jet-black skin with iridescent blue violet and bronze hexagonal scales "
     "catching the light, razor sharp individual scale texture, realistic specular "
     "highlights and skin pores. The snake body forms a loose elegant S-shaped coil "
     "lying horizontally, the full head clearly visible at the LEFT end with a glossy "
     "dark eye and defined jaw, the body tapers smoothly to a fine pointed tail at the "
     "RIGHT end. Studio product photography, soft even lighting, 100mm macro lens, "
     "shallow depth of field, isolated on a pure solid white background, no shadow, "
     "no ground, no reflections, no props, no text, ultra detailed, real life snake skin"),
    ("snake_flux2_B", 2688, 1344,
     "Extreme photorealistic close-up of a real black snake, glossy obsidian skin with "
     "shimmering iridescent violet and gold hexagonal scales, extremely detailed natural "
     "scale texture, wet specular highlights. The snake is stretched in a gentle flowing "
     "S-curve lying horizontally, head at the LEFT end clearly visible in profile with a "
     "dark glossy eye, body narrowing gradually to a thin tail tip at the RIGHT end. "
     "Clean studio lighting, macro photography, pure solid white background, no shadow, "
     "no surface, no text, photorealistic, real life, high detail"),
]

ENDPOINTS = [
    "https://api.bfl.ai/v1/flux-2-pro-preview",
    "https://api.bfl.ai/v1/flux-2-pro",
]


def _post(url, key, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"x-key": key, "accept": "application/json",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def _get(url, key, request_id=None):
    url = url + (f"?id={request_id}" if request_id else "")
    req = urllib.request.Request(
        url, method="GET",
        headers={"x-key": key, "accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def generate(name, w, h, prompt, key, endpoint):
    print(f"-> {name}  {w}x{h}  ({endpoint.rsplit('/', 1)[-1]})")
    payload = {"prompt": prompt, "width": w, "height": h, "output_format": "jpeg"}
    try:
        res = _post(endpoint, key, payload)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        raise SystemExit(f"  HTTP {e.code} from {endpoint}\n  {detail}")

    polling = res.get("polling_url") or f"https://api.bfl.ai/v1/get_result"
    rid = res.get("id")
    for attempt in range(120):
        time.sleep(1.0 if attempt < 20 else 2.0)
        st = _get(polling, key, rid)
        status = st.get("status")
        if status == "Ready":
            url = st["result"]["sample"]
            out = os.path.join(RAW, name + ".jpg")
            with urllib.request.urlopen(url, timeout=120) as r, open(out, "wb") as fh:
                fh.write(r.read())
            print(f"  saved {out}")
            return out
        if status in ("Error", "Failed"):
            raise SystemExit(f"  generation failed: {json.dumps(st)[:400]}")
    raise SystemExit("  timed out waiting for FLUX.2")


def main():
    key = os.environ.get("BFL_API_KEY")
    if not key:
        raise SystemExit(
            "BFL_API_KEY is not set.\n"
            "  1. create a key at https://bfl.ai\n"
            "  2. export BFL_API_KEY=<your key>\n"
            "  3. python3 tools/gen_flux2.py"
        )
    os.makedirs(RAW, exist_ok=True)

    last = None
    for ep in ENDPOINTS:
        try:
            for name, w, h, p in PROMPTS:
                generate(name, w, h, p, key, ep)
            break
        except SystemExit as e:
            print(f"  {e}")
            last = e
    else:
        raise SystemExit(f"no endpoint worked; last error:\n{last}")

    print("\nNext: re-run the asset pipeline against the new source.")
    print("  python3 tools/make_sprite.py assets/raw/snake_flux2_A.jpg \\")
    print("      assets/final/snake.png assets/final/snake.json")
    print("  python3 tools/extract_parts.py")
    print("  python3 tools/preview.py")
    print("\nIf the anchors change, paste the new head block from")
    print("assets/final/snake_assets.json over ASSET.head in src/game.js.")


if __name__ == "__main__":
    main()
