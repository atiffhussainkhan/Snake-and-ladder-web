# Snake &amp; Ladder — Real Skin

A complete, self-contained Snake &amp; Ladder game. Photorealistic snake skin, head
anchored to the bite square and tail anchored to the landing square, 1–4 player
tournaments of 1/3/5/7/9 games.

**No build step. No server. No dependencies. Nothing to install.**

---

## Run it right now

**Option A — just open it**
Double-click `index.html`. It runs straight from `file://`.

**Option B — one self-contained file (best for testing on your phone)**
`dist/snake-ladder.html` is the entire game in a single 7 MB file with every image
embedded. AirDrop it, email it, or put it on any static host and open it. No
folders, no path resolution, no server.

**Option C — a local server (only if you prefer http)**
```bash
python3 -m http.server 8000
# then open http://localhost:8000/
```

---

## Put it online

This folder is upload-ready. Everything is referenced by **relative paths**, so it
works unchanged at a domain root, in a subdirectory, or on a project page.

### GitHub Pages (free)

```bash
cd snake-ladder-game
git init
git add .
git commit -m "Snake and Ladder — real skin"
git branch -M main
git remote add origin https://github.com/<you>/snake-and-ladder.git
git push -u origin main
```
Then **Settings → Pages → Source: `main` / root**. Your game appears at
`https://<you>.github.io/snake-and-ladder/` in about a minute.

### Netlify / Vercel / Cloudflare Pages

Drag the `snake-ladder-game` folder onto the dashboard. No build command, no
output directory — just publish. (Do **not** upload the `dist/` folder on its own
unless you only want the single-file version.)

### Any other static host

Upload everything, keep the folder structure, and serve `index.html` as the
default document. There is nothing server-side to configure.

---

## What's where

```
index.html                  the game
src/game.js                 board, snakes, tournament, animation
src/style.css               all styling, incl. the 3D board tilt
assets/final/               everything the page loads
  snake.png                 full snake, transparent background
  snake_head.png            head + neck, feathered for seamless blending
  snake_skin.png            scale texture used as the body fill
  avatars/                  4 player portraits + die_1..die_6
  favicon-*.png icon-512    icons, cut from the same snake art
assets/raw/                 generation sources (not loaded at runtime)
dist/snake-ladder.html      the whole game as one file
tools/                      the asset pipeline + tests
```

`assets/raw/` and the `tools/` folder are **not** needed to play or to host. They
are kept so the art can be regenerated — see `tools/DEV-NOTES.md`.

---

## How to play

1. **First page** — tap portraits to select **1–4 players**, then pick
   **1, 3, 5, 7 or 9** games. Hit **Start tournament**.
2. **Roll dice** (or press Space).
3. You must land **exactly on 100**. A snake's head on a square bites you and
   slides you to its tail; a ladder takes you up. The head sits on the square
   that bites, the tail on the square you land on.
4. Each game ends the moment someone reaches 100. The next game starts
   automatically — the first page only comes back after the **whole tournament**.
5. The results screen names the tournament winner.

---

## Notes on the assets

The snake skin, player portraits and dice body are **AI-generated**, then
processed into game-ready assets:

- the snake's background is removed with a real alpha matte and the white fringe
  is removed with the **compositing equation** (`subject = 255 + (observed-255)/a`),
  which is what keeps the scale edges clean
- the head and tail anchors were **measured automatically** by running PCA over
  the alpha mask — the head is whichever end of the coil's principal axis is
  thicker, since a snake tapers to a point at the tail
- the dice pips are **drawn programmatically**, not generated, so all six faces
  are provably correct (verified by connected-component counting)

**These were not made with FLUX.2.** No Black Forest Labs key was available, and
the generator used exposes no model selector. To regenerate with genuine FLUX.2:

```bash
export BFL_API_KEY=...        # https://bfl.ai
python3 tools/gen_flux2.py
python3 tools/make_sprite.py assets/raw/snake_flux2_A.jpg \
        assets/final/snake.png assets/final/snake.json
python3 tools/extract_parts.py
python3 tools/make_ui_assets.py
python3 tools/make_release.py
```

`tools/DEV-NOTES.md` documents the full pipeline, the anchoring maths, the board
design rules, and the test suite.

---

## Testing

The game logic is covered by an automated stress suite: **122 games · 8,197
rolls · 136,575 assertions · 0 failures**, across every player count crossed
with every tournament length, plus deliberate mid-tournament quits. See
`tools/DEV-NOTES.md`.
