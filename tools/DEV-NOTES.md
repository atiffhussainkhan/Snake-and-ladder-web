# Snake & Ladder — photoreal skin, tournaments up to 4 players

Playable in any browser. No build step, no server, no dependencies.

```
open index.html
```

![board](assets/final/preview_board.png)

## Screens

**Lobby (first page)** — tap portraits to select **1–4 players**, then choose
**1, 3, 5, 7 or 9** games. Each game option carries a short blurb.

**Game** — 10×10 board, one die, per-player scorecard. The header shows
`Game n of N`.

**Results** — tournament winner, then a standings table (won / best finish /
squares advanced). `Back to main page` returns to the lobby.

### Tournament rules

- A tournament is **exactly** the chosen number of games — 5 selected means 5
  games are played, no more, no fewer.
- A game ends the moment a player lands **exactly on 100** (overshooting means
  you stay put and must roll the precise remainder). The game is over, full stop.
- 1 point per game won. Ties break on best finishing rank, then squares advanced.
- **The lobby is never shown between games.** After each game a short
  "Game *n* of N" interstitial plays and the next game starts immediately.
  The results screen appears only after the final game.

## Snake anchoring

For every snake `[from, to]`:

- the **face** sits on `from` — the bite square that sends a player down
- the **tail tip** sits on `to` — the landing square
- the **nose points away from the body**, because the head leads

`assets/final/preview_anchors.png` draws both anchors on every snake.

## Movement animation

Movement is **one square at a time** — a short hop per square, then the next,
then the next. Ladders are climbed square by square. Snake bites slide the token
down the exact polyline the body was drawn from.

That last point is why `snakePathFor()` is shared: the renderer and the
animation call the same function, so the token can never slide somewhere the
snake is not.

Animation is driven by **wall-clock time, not frame counts**. The first version
advanced one waypoint per `requestAnimationFrame` tick, and the 151-point snake
path needed 151 ticks — a throttled or backgrounded tab turned a 2.5-second bite
into minutes and the game looked hung. Time-driven, a bite always completes in
~0.85s whatever the frame rate.

## How the anchors are produced

`tools/make_sprite.py`, in order:

1. soft alpha matte from the white studio backdrop (256-entry LUT, so the work
   stays inside PIL's C loops)
2. shadow and white-fringe removal via the **compositing equation** — a pixel
   over white obeys `observed = subject·a + 255(1−a)`, so
   `subject = 255 + (observed−255)/a`. Inverting it is what removes the pale halo
   around every scale edge; plain erosion does not.
3. **PCA over the alpha mask** to find the coil's principal axis
4. the two extremes of that axis, and the **thicker** end is called the head — a
   snake tapers to a point at the tail, so thickness is a reliable discriminator

Shipped asset: head `(192, 648)`, tail `(2667, 512)`, head thickness `308px`
vs tail `168px`.

## Why the snake is split into head + skin

A coiled snake photo has a fixed aspect ratio. Squeezed to span two squares it is
obese; across nine squares it goes paper-thin. No single transform fixes both. So
the geometry is generated per-snake and filled with the real scale texture, with
the photoreal head composited on top, keeping a believable thickness at any
distance. The body ramps from thin to full width over about a third of a square
so it emerges from under the head instead of stepping against the head plate's
off-axis neck.

A **Photo Coil** toggle places the single un-split photo with a similarity
transform solved from the measured anchors (both constraints exact). It is there
to show the literal one-image result, and it inherits the aspect-ratio problem,
which is why **Real Skin** is the default.

## Dice and player portraits

All UI art is AI-generated. Not FLUX.2 — see the caveat below.

- `tools/make_ui_assets.py` cuts the four portraits into circular RGBA avatars
  framed on the face.
- The die is built from **one photoreal blank die face with the pips drawn
  programmatically**. A generated "dice showing 4 pips" cannot be trusted to
  show exactly 4, and a board game whose die lies about its roll is broken. The
  die body is the AI image; only the pips are drawn, so all six faces are exact.
  `tools/make_ui_assets.py` was checked with connected-component blob counting:
  every face reports the expected pip count.

## Regenerating with real FLUX.2

FLUX.2 is **not** used in this build — no BFL key was available when the assets
were made, and the generator used exposes no model selector. To swap it in:

```bash
export BFL_API_KEY=...        # https://bfl.ai
python3 tools/gen_flux2.py    # POST /v1/flux-2-pro-preview
python3 tools/make_sprite.py assets/raw/snake_flux2_A.jpg \
        assets/final/snake.png assets/final/snake.json
python3 tools/extract_parts.py
python3 tools/make_ui_assets.py
```

Then paste the new `ASSET.head` block from `assets/final/snake_assets.json` over
the one in `src/game.js`. Values are inlined rather than fetched so the game runs
from `file://`.

FLUX.2 [pro] bills from ~$0.03/megapixel, so a 2688×1344 image is ~$0.11.
[klein] 4B is ~10× cheaper and better for iterating on the look.

## Layout

```
index.html                    lobby + game + results
src/game.js                   geometry, snake renderers, tournament, animation
src/style.css
assets/raw/                   generated sources (untouched)
assets/final/snake.png        full snake, transparent
assets/final/snake_head.png   head + neck, edge-feathered
assets/final/snake_skin.png   scale texture used as the body fill
assets/final/avatars/         4 circular portraits + die_1..6.png
assets/final/snake_assets.json  measured anchors
assets/final/preview_*.png    rendered proofs
tools/make_sprite.py          matte + decontamination + PCA anchor detection
tools/extract_parts.py        split into head/skin, measure plate anchors
tools/make_ui_assets.py       circular avatars + programmatic dice pips
tools/preview.py              offline renderer mirroring game.js geometry
tools/gen_flux2.py            real FLUX.2 generation
```

`tools/preview.py` deliberately reimplements the same geometry as
`src/game.js`. It is the reference implementation — but note it is **not** a
substitute for testing the real page: it has no animation engine and no
duplicate-identifier risk, so it stayed green through a browser-breaking bug.
Verify in the browser.

## Testing

`tools/make_stress.py` builds a runnable stress variant of the game and
`tools/stress_harness.js` drives it. The variant is generated by **mechanical
substitution of exactly five timing constants** — `sleep`, the two animation
durations, and the two game-transition timers — and the build script asserts the
diff contains nothing else, so the code under test cannot drift from what ships.
No test code is ever in `src/`.

```bash
python3 tools/make_stress.py
open "http://127.0.0.1:8765/index.stress.html?stress=1&run=<id>"
```

Last full run: **122 games · 8,197 rolls · 136,575 assertions · 0 failures**,
covering every player count (1–4) crossed with every tournament length
(1/3/5/7/9), plus deliberate mid-tournament quits.

Invariants asserted after **every single roll**:

- positions are integers within [0, 100]; 100 is only ever reached on an exact
  roll, never overshot
- the token's drawn position is within 2.5px of its square's centre, and lift /
  scale are back to rest (catches "stuck mid-hop")
- exactly one player is active, and it is the current player
- `gameIndex` stays in `[1, totalGames]` and never advances mid-game
- tournament points always equal games completed
- the lobby is **never** shown between games of a tournament
- results appear only after the final game, with the right row count and a winner
  drawn from the roster
- `validateBoard()` reports no ladder/snake rule violations

Two genuine product bugs were found this way and fixed:

1. **`game.busy` was never cleared when a player won.** `roll()` returns straight
   after `finishGame()`, so the lock stayed `true` forever. It was masked because
   `startGame()` and the lobby both rebuild the game object — except the final
   game goes to `showResults()`, which left the flag permanently wedged.
2. **The board could be built before its sprites had loaded**, and `drawImage()`
   with a null image threw and took the whole game down. `buildStatic()` and
   `startFromLobby()` now refuse to run until assets are present and report
   loudly instead of rendering a blank board.

The harness itself had four bugs worth noting, because each one produced a
*convincing* false failure that looked like a product defect: `inv()` not
returning its condition (so `!inv(...)` was always true and the loop broke on the
first `game.over` iteration), a `const` reassigned in the abort path, a wall-clock
deadline too short for 9-game tournaments, and two stress pages beaconing into
one log with no run id to separate them.

## Notes

- `Image.transform()` is broken in the Pillow 11.3.0 build on this machine (even
  `EXTENT` returns an empty layer), so `tools/preview.py` builds the head
  placement from `resize` + `rotate`. The browser renderer uses
  `ctx.setTransform` and is unaffected.
- If an error ever blanks the page, a red banner shows at the top and the message
  is beaconed to the dev server, so failures are self-diagnosing.
- Commercial use is fine: BFL API output carries full commercial rights and
  paid-tier Google image output is not used for training. If self-hosting
  instead, only FLUX.2 [klein] **4B** is Apache 2.0; 9B and [dev] are
  non-commercial.
