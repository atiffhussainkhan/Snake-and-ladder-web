/* =========================================================================
   Snake & Ladder — photoreal skin renderer
   -------------------------------------------------------------------------
   Screens:  lobby -> (game x N) -> results -> lobby

   Tournament rules
     * A tournament is exactly the chosen number of games (1/3/5/7/9).
     * Each game is played to completion: first player to land exactly on 100
       wins that game and the game ends immediately.
     * 1 point per game won. Ties broken by best finishing rank, then by total
       squares advanced.
     * Between games the lobby is NOT shown — play advances straight to the next
       game behind a short "Game n of N" interstitial.
     * After the final game the results screen names the winner, then returns
       to the lobby.

   Snake contract
     head  -> anchored to the BITE square   (the square that sends you down)
     tail  -> anchored to the LANDING square (where you end up)
   ========================================================================= */
'use strict';

/* ------------------------------ board ---------------------------------- */
const GRID = 10;
const CELLS = GRID * GRID;
const PAD = 26;
const CSS = 1240;
const CELL = (CSS - PAD * 2) / GRID;
const GAP = 4;    // gutter between tiles, so the bevel has somewhere to read
const RAD = 0.16;  // tile corner radius, as a fraction of the tile size

/* [from, to] — from is the BITE square, to is the LANDING square. */
const SNAKES = [
  [16, 6], [47, 26], [49, 11], [56, 53], [62, 19],
  [64, 60], [87, 24], [93, 73], [95, 75], [98, 78],
];
/* Board design rules, enforced by validateBoard() at startup:
     - a ladder may not START on square 1 (everyone begins there, so it would be
       a free ride on the opening roll)
     - a ladder may not END on 99 or 100 (reaching 100 must be earned on a roll)
     - a ladder may not start or end on a snake's face (that square belongs to
       the snake, not the ladder)
     - ladders climb, snakes descend                                                 */
const LADDER_NO_START = [1];
const LADDER_NO_END = [99, 100];
const LADDERS = [
  [4, 14], [9, 31], [21, 42], [28, 84],
  [36, 44], [51, 67], [71, 91], [80, 96],
];

function validateBoard() {
  const heads = new Set(SNAKES.map((s) => s[0]));
  const problems = [];
  for (const [a, b] of LADDERS) {
    if (b <= a) problems.push(`ladder ${a}->${b} does not climb`);
    if (LADDER_NO_START.includes(a)) problems.push(`ladder ${a}->${b} must not start at ${a}`);
    if (LADDER_NO_END.includes(b)) problems.push(`ladder ${a}->${b} must not end at ${b}`);
    if (heads.has(a)) problems.push(`ladder ${a}->${b} starts on a snake face`);
    if (heads.has(b)) problems.push(`ladder ${a}->${b} ends on a snake face`);
  }
  for (const [a, b] of SNAKES) {
    if (b >= a) problems.push(`snake ${a}->${b} does not descend`);
  }
  const starts = LADDERS.map((l) => l[0]);
  if (new Set(starts).size !== starts.length) problems.push('two ladders share a start square');
  return problems;
}

/* --------------------------- players / assets -------------------------- */
const ROSTER = [
  { name: 'Player 1', colour: '#4cc2ff', avatar: 'assets/final/avatars/avatar_p1.png' },
  { name: 'Player 2', colour: '#ff7a59', avatar: 'assets/final/avatars/avatar_p2.png' },
  { name: 'Player 3', colour: '#f2c14e', avatar: 'assets/final/avatars/avatar_p3.png' },
  { name: 'Player 4', colour: '#7ee08a', avatar: 'assets/final/avatars/avatar_p4.png' },
];
const GAME_OPTIONS = [1, 3, 5, 7, 9];
const GAME_BLURB = {
  1: 'Single match — one game decides it.',
  3: 'Best of three. Fast.',
  5: 'Best of five. The classic length.',
  7: 'Long haul. Seven games, most wins takes it.',
  9: 'Full marathon. Nine games, no mercy.',
};

const ASSET = {
  head:  { face: [200, 250], neck: [716, 151], facingDeg: 165, w: 782, h: 411 },
  skin:  { w: 620, h: 330 },
  sprite: {
    w: 2882, h: 809,
    head: [192.08, 648.18],
    tail: [2666.98, 511.97],
  },
};

const TUNING = {
  headLenFrac: 0.85,
  bodyWidthFrac: 0.32,
  wobbleFrac: 0.125,
  waves: 1.7,
  samples: 150,
  hopMs: 150,        // per-square hop
  glideTotalMs: 820, // whole snake slide, regardless of path length
};

/* ------------------------------ assets --------------------------------- */
const img = { head: null, skin: null, sprite: null, skinPattern: null };
const avatars = [];   // Image objects for the selected roster
const dieImgs = [];   // dieImgs[1..6]
const $ = (id) => document.getElementById(id);

function loadImage(src) {
  return new Promise((res, rej) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = () => rej(new Error('missing asset: ' + src));
    i.src = src;
  });
}

function loadImages() {
  return Promise.all([
    loadImage('assets/final/snake_head.png'),
    loadImage('assets/final/snake_skin.png'),
    loadImage('assets/final/snake.png'),
    ...ROSTER.map((p) => loadImage(p.avatar)),
    ...[1, 2, 3, 4, 5, 6].map((n) => loadImage(`assets/final/avatars/die_${n}.png`)),
  ]).then((all) => {
    img.head = all[0]; img.skin = all[1]; img.sprite = all[2];
    ROSTER.forEach((p, i) => { avatars[i] = all[3 + i]; });
    for (let n = 1; n <= 6; n++) dieImgs[n] = all[3 + ROSTER.length + n - 1];
  });
}

/* ----------------------------- geometry -------------------------------- */
function squareToCell(n) {
  const i = n - 1;
  const row = Math.floor(i / GRID);
  let col = i % GRID;
  if (row % 2 === 1) col = GRID - 1 - col;
  return { col, row };
}
function centreOf(n) {
  const { col, row } = squareToCell(n);
  return {
    x: PAD + (col + 0.5) * CELL,
    y: PAD + (GRID - 1 - row + 0.5) * CELL,
  };
}

function serpentine(A, B) {
  const dx = B.x - A.x, dy = B.y - A.y;
  const D = Math.hypot(dx, dy) || 1;
  const ux = dx / D, uy = dy / D;
  const vx = -uy, vy = ux;
  const amp = D * TUNING.wobbleFrac;
  const pts = [];
  for (let k = 0; k <= TUNING.samples; k++) {
    const t = k / TUNING.samples;
    const pin = Math.sin(Math.PI * t);
    const off = Math.sin(t * Math.PI * TUNING.waves) * amp * pin;
    pts.push({ x: A.x + dx * t + vx * off, y: A.y + dy * t + vy * off, t });
  }
  return pts;
}

/* The drawn body and the bite animation MUST share this path, or the token
   would slide somewhere the snake is not. */
function snakePathFor(from, to) { return serpentine(centreOf(from), centreOf(to)); }

function tubeFrame(pts, maxW) {
  return pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    let tx = b.x - a.x, ty = b.y - a.y;
    const L = Math.hypot(tx, ty) || 1; tx /= L; ty /= L;
    return {
      x: p.x, y: p.y, t: p.t, tx, ty, nx: -ty, ny: tx,
      w: maxW * (0.5 + 0.5 * Math.cos(Math.PI * Math.pow(p.t, 1.5)))
            * Math.min(1, 0.42 + p.t * 9.0),
    };
  });
}

function traceRibbon(ctx, fr, scale, lo, hi) {
  ctx.beginPath();
  for (let i = lo; i <= hi; i++) {
    const p = fr[i], w = Math.max(0.25, p.w * scale);
    const x = p.x + p.nx * w, y = p.y + p.ny * w;
    i === lo ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  for (let i = hi; i >= lo; i--) {
    const p = fr[i], w = Math.max(0.25, p.w * scale);
    ctx.lineTo(p.x - p.nx * w, p.y - p.ny * w);
  }
  ctx.closePath();
}

function shadeTube(ctx, fr, lo, hi, scale, stops) {
  for (let i = lo; i < hi; i++) {
    const p = fr[i], w = Math.max(0.25, p.w * scale);
    const g = ctx.createLinearGradient(
      p.x + p.nx * w, p.y + p.ny * w,
      p.x - p.nx * w, p.y - p.ny * w);
    for (const [o, c] of stops) g.addColorStop(o, c);
    ctx.fillStyle = g;
    ctx.beginPath();
    const a = fr[i], b = fr[i + 1];
    const aw = Math.max(0.25, a.w * scale), bw = Math.max(0.25, b.w * scale);
    ctx.moveTo(a.x + a.nx * aw, a.y + a.ny * aw);
    ctx.lineTo(b.x + b.nx * bw, b.y + b.ny * bw);
    ctx.lineTo(b.x - b.nx * bw, b.y - b.ny * bw);
    ctx.lineTo(a.x - a.nx * aw, a.y - a.ny * aw);
    ctx.closePath();
    ctx.fill();
  }
}

function drawHead(ctx, at, angle, scale) {
  const [fx, fy] = ASSET.head.face;
  ctx.save();
  ctx.translate(at.x, at.y);
  ctx.rotate(angle);
  ctx.scale(scale, scale);
  ctx.drawImage(img.head, -fx, -fy);
  ctx.restore();
}

/* ---------------------------- snake renderers -------------------------- */
function renderSnakeSkin(ctx, from, to, highlight) {
  const bite = centreOf(from), land = centreOf(to);
  const headScale = (TUNING.headLenFrac * CELL) / ASSET.head.w;
  const travel = Math.atan2(land.y - bite.y, land.x - bite.x);

  ctx.save();
  if (highlight) { ctx.shadowColor = 'rgba(255,90,90,.8)'; ctx.shadowBlur = 26; }

  const pts = snakePathFor(from, to);
  const maxW = (TUNING.bodyWidthFrac * CELL) / 2;
  const fr = tubeFrame(pts, maxW);

  ctx.save();
  ctx.translate(0, CELL * 0.05);
  ctx.filter = 'blur(6px)';
  traceRibbon(ctx, fr, 1.06, 0, fr.length - 1);
  ctx.fillStyle = 'rgba(0,0,0,.42)';
  ctx.fill();
  ctx.restore();

  traceRibbon(ctx, fr, 1, 0, fr.length - 1);
  ctx.save();
  ctx.clip();
  shadeTube(ctx, fr, 0, fr.length - 1, 1, [
    [0.00, '#05070b'], [0.26, '#39414f'], [0.46, '#5d6879'],
    [0.62, '#2b323d'], [1.00, '#04060a'],
  ]);
  if (img.skinPattern) {
    ctx.globalCompositeOperation = 'overlay';
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = img.skinPattern;
    ctx.fillRect(0, 0, CSS, CSS);
  }
  ctx.globalCompositeOperation = 'screen';
  ctx.globalAlpha = 0.5;
  shadeTube(ctx, fr, 0, fr.length - 1, 0.30, [
    [0, 'rgba(0,0,0,0)'], [0.5, 'rgba(190,215,255,.5)'], [1, 'rgba(0,0,0,0)'],
  ]);
  ctx.restore();

  traceRibbon(ctx, fr, 1, 0, fr.length - 1);
  ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(1.4, CELL * 0.016);
  ctx.strokeStyle = 'rgba(4,6,10,.85)';
  ctx.stroke();

  drawHead(ctx, bite, travel + Math.PI - (ASSET.head.facingDeg * Math.PI / 180), headScale);
  ctx.restore();
}

function renderSnakePhoto(ctx, from, to) {
  if (!img.sprite) return;
  const bite = centreOf(from), land = centreOf(to);
  const S = ASSET.sprite;
  const ux = S.tail[0] - S.head[0], uy = S.tail[1] - S.head[1];
  const L = Math.hypot(ux, uy);
  const gamma = Math.atan2(uy, ux);
  const beta = Math.atan2(land.y - bite.y, land.x - bite.x);
  const D = Math.hypot(land.x - bite.x, land.y - bite.y);
  const sLen = D / L;
  const sPerp = Math.min(sLen, (CELL * 0.62) / (S.h || 1));
  ctx.save();
  ctx.translate(bite.x, bite.y);
  ctx.rotate(beta - gamma);
  ctx.scale(sLen, sPerp);
  ctx.rotate(-gamma);
  ctx.translate(-S.head[0], -S.head[1]);
  ctx.drawImage(img.sprite, 0, 0);
  ctx.restore();
}

/* ------------------------------ board ---------------------------------- */
function paintBoard(ctx) {
  ctx.clearRect(0, 0, CSS, CSS);

  // outer slab — a thick beveled frame the play surface sits inside
  const g = ctx.createLinearGradient(0, 0, CSS * 0.7, CSS);
  g.addColorStop(0, '#33405a');
  g.addColorStop(0.5, '#1d2433');
  g.addColorStop(1, '#10141d');
  roundRect(ctx, 4, 4, CSS - 8, CSS - 8, 30);
  ctx.fillStyle = g;
  ctx.fill();

  // top lip highlight on the slab
  ctx.save();
  roundRect(ctx, 4, 4, CSS - 8, CSS - 8, 30);
  ctx.clip();
  ctx.lineWidth = 7;
  roundRect(ctx, 8, 8, CSS - 16, CSS - 16, 26);
  ctx.strokeStyle = 'rgba(255,255,255,.20)';
  ctx.stroke();
  ctx.restore();

  // recessed well — inner shadow reads as depth
  const well = PAD - 12;
  ctx.save();
  roundRect(ctx, well, well, CSS - well * 2, CSS - well * 2, 20);
  const wg = ctx.createLinearGradient(0, well, 0, CSS - well);
  wg.addColorStop(0, '#0b0e15');
  wg.addColorStop(1, '#141a25');
  ctx.fillStyle = wg;
  ctx.fill();
  ctx.clip();
  ctx.lineWidth = 16;
  roundRect(ctx, well + 8, well + 8, CSS - well * 2 - 16, CSS - well * 2 - 16, 16);
  ctx.strokeStyle = 'rgba(0,0,0,.55)';
  ctx.stroke();
  ctx.restore();

  for (let n = 1; n <= CELLS; n++) {
    const { col, row } = squareToCell(n);
    const x = PAD + col * CELL, y = PAD + (GRID - 1 - row) * CELL;
    const light = (row + col) % 2 === 0;
    const finish = n === CELLS, start = n === 1;
    const fill = finish ? '#4a3a12' : start ? '#0f4a5e' : (light ? '#fbeed3' : '#bcd6f2');

    const gx = x + GAP / 2, gy = y + GAP / 2;
    const gw = CELL - GAP, gh = CELL - GAP;
    const rad = gh * RAD;

    // cast shadow so the tile sits above the board
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.45)';
    ctx.shadowBlur = gh * 0.07;
    ctx.shadowOffsetY = gh * 0.035;
    roundRect(ctx, gx, gy, gw, gh, rad);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.restore();

    // body
    const sg = ctx.createLinearGradient(gx, gy, gx, gy + gh);
    sg.addColorStop(0, shade(fill, 0.13));
    sg.addColorStop(0.55, fill);
    sg.addColorStop(1, shade(fill, -0.12));
    roundRect(ctx, gx, gy, gw, gh, rad);
    ctx.fillStyle = sg;
    ctx.fill();

    // bevel: light top-left lip, dark bottom-right lip => raised
    ctx.save();
    roundRect(ctx, gx, gy, gw, gh, rad);
    ctx.clip();
    const bw = Math.max(2, gh * 0.06);
    ctx.lineWidth = bw;
    roundRect(ctx, gx + bw, gy + bw, gw - bw * 2, gh - bw * 2, Math.max(1, rad - bw));
    ctx.strokeStyle = 'rgba(255,255,255,.72)';
    ctx.stroke();
    roundRect(ctx, gx - bw, gy - bw, gw + bw * 2, gh + bw * 2, rad + bw);
    ctx.strokeStyle = 'rgba(14,20,32,.42)';
    ctx.stroke();
    ctx.restore();

    // gloss sweep
    const gl = ctx.createLinearGradient(gx, gy, gx + gw * 0.62, gy + gh * 0.72);
    gl.addColorStop(0, 'rgba(255,255,255,.34)');
    gl.addColorStop(0.42, 'rgba(255,255,255,.06)');
    gl.addColorStop(1, 'rgba(255,255,255,0)');
    roundRect(ctx, gx, gy, gw, gh, rad);
    ctx.fillStyle = gl;
    ctx.fill();

    // embossed number
    const cx = x + CELL / 2, cy = y + CELL / 2;
    ctx.font = `800 ${Math.round(CELL * 0.19)}px Inter, system-ui, sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = (finish || start) ? 'rgba(0,0,0,.45)' : 'rgba(255,255,255,.5)';
    ctx.fillText(String(n), cx, cy + CELL * 0.011);
    ctx.fillStyle = (finish || start) ? 'rgba(255,255,255,.92)' : 'rgba(44,54,74,.92)';
    ctx.fillText(String(n), cx, cy);
  }

  // polished sweep over the whole playing surface
  const sheen = ctx.createLinearGradient(0, 0, CSS * 0.85, CSS * 0.95);
  sheen.addColorStop(0, 'rgba(255,255,255,.10)');
  sheen.addColorStop(0.30, 'rgba(255,255,255,.02)');
  sheen.addColorStop(0.55, 'rgba(255,255,255,0)');
  ctx.fillStyle = sheen;
  ctx.fillRect(0, 0, CSS, CSS);

  ctx.font = `800 ${Math.round(CELL * 0.125)}px Inter, system-ui, sans-serif`;
  ctx.textAlign = 'left';
  ctx.fillStyle = 'rgba(0,0,0,.4)';
  ctx.fillText('START', PAD + 8, CSS - PAD - CELL * 0.175 + 1.5);
  ctx.fillStyle = 'rgba(120,255,190,.95)';
  ctx.fillText('START', PAD + 8, CSS - PAD - CELL * 0.175);
  ctx.textAlign = 'right';
  ctx.fillStyle = 'rgba(0,0,0,.4)';
  ctx.fillText('FINISH', CSS - PAD - 8, PAD + CELL * 0.205 + 1.5);
  ctx.fillStyle = 'rgba(255,214,120,.95)';
  ctx.fillText('FINISH', CSS - PAD - 8, PAD + CELL * 0.205);
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.lineTo(x + w - rr, y); ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
  ctx.lineTo(x + w, y + h - rr); ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
  ctx.lineTo(x + rr, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
  ctx.lineTo(x, y + rr); ctx.quadraticCurveTo(x, y, x + rr, y);
  ctx.closePath();
}

function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  if (amt > 0) { r += (255 - r) * amt; g += (255 - g) * amt; b += (255 - b) * amt; }
  else { r *= 1 + amt; g *= 1 + amt; b *= 1 + amt; }
  const h = (v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
  return `#${h(r)}${h(g)}${h(b)}`;
}

function drawLadders(ctx) {
  for (const [a, b] of LADDERS) {
    const A = centreOf(a), B = centreOf(b);
    const dx = B.x - A.x, dy = B.y - A.y;
    const L = Math.hypot(dx, dy) || 1;
    const nx = -dy / L, ny = dx / L;
    const half = CELL * 0.17;
    // Rail separation; rungs span exactly rail to rail.
    const RAIL_GAP = CELL * 0.30;
    const rail = (o) => {
      ctx.beginPath();
      ctx.moveTo(A.x + nx * (half + o), A.y + ny * (half + o));
      ctx.lineTo(B.x + nx * (half + o), B.y + ny * (half + o));
      ctx.lineWidth = CELL * 0.055;
      ctx.strokeStyle = '#8a5a2b';
      ctx.lineCap = 'round';
      ctx.stroke();
      ctx.lineWidth = CELL * 0.026;
      ctx.strokeStyle = '#c98b46';
      ctx.stroke();
    };
    rail(0); rail(-RAIL_GAP);
    const steps = Math.max(3, Math.round(L / RAIL_GAP));
    ctx.lineWidth = CELL * 0.032;
    ctx.strokeStyle = '#b97c3c';
    for (let k = 1; k < steps; k++) {
      const t = k / steps;
      const px = A.x + dx * t, py = A.y + dy * t;
      ctx.beginPath();
      ctx.moveTo(px + nx * (half - RAIL_GAP), py + ny * (half - RAIL_GAP));
      ctx.lineTo(px + nx * half, py + ny * half);
      ctx.stroke();
    }
  }
}

const canvas = $('board');
const ctx = canvas.getContext('2d');
let staticLayer = null;
let mode = 'skin';
let litSnake = null;

function buildStatic() {
  // Never build the board from sprites that have not arrived. drawImage() with
  // a null image throws and would take the whole game down, so fail loudly and
  // visibly instead of rendering a blank board.
  if (!img.head || !img.skin || !img.sprite) {
    console.error('buildStatic called before snake assets finished loading');
    return;
  }
  staticLayer = document.createElement('canvas');
  staticLayer.width = CSS; staticLayer.height = CSS;
  const c = staticLayer.getContext('2d');
  paintBoard(c);
  drawLadders(c);
  for (const [from, to] of SNAKES) {
    if (mode === 'photo') renderSnakePhoto(c, from, to);
    else renderSnakeSkin(c, from, to, litSnake === from);
  }
}

/* ======================= tokens + animation =========================== */
/* vis[i] is the drawn position of player i.
   Animation is driven by WALL-CLOCK time across whole legs, never by counting
   frames. The earlier version advanced one waypoint per rAF tick, so the 151
   point snake path needed 151 ticks: a throttled or backgrounded tab turned a
   2.5 second bite into minutes and the game appeared to hang. Time driven, a
   slide always finishes on schedule and simply renders at whatever fps it
   manages. */
const vis = [];
let anim = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const easeInOut = (u) => (u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2);

/* One leg = a polyline travelled over a fixed duration. Hops get a vertical
   arc; glides (snake slides) stay on the ground. */
function makeLeg(from, pts, dur, hop) {
  const poly = [from, ...pts];
  const cum = [0];
  for (let i = 1; i < poly.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(poly[i].x - poly[i - 1].x, poly[i].y - poly[i - 1].y));
  }
  return { poly, cum, dur, hop, len: cum[cum.length - 1] };
}

function pointAt(leg, d) {
  const { poly, cum } = leg;
  if (d <= 0) return poly[0];
  for (let i = 1; i < poly.length; i++) {
    if (d <= cum[i] || i === poly.length - 1) {
      const seg = Math.max(1e-6, cum[i] - cum[i - 1]);
      const u = (d - cum[i - 1]) / seg;
      return {
        x: poly[i - 1].x + (poly[i].x - poly[i - 1].x) * u,
        y: poly[i - 1].y + (poly[i].y - poly[i - 1].y) * u,
      };
    }
  }
  return poly[poly.length - 1];
}

/* One short hopping leg per square: step, hop, step, hop... */
function hopLegs(points) {
  const legs = [];
  let prev = null;
  for (const p of points) {
    legs.push(makeLeg(prev || p, [p], TUNING.hopMs, true));
    prev = p;
  }
  return legs;
}

function animateLegs(idx, legs) {
  if (!legs.length) return Promise.resolve();
  return new Promise((resolve) => {
    anim = { idx, legs, t0: 0, resolve,
             total: legs.reduce((s, l) => s + l.dur, 0) };
    requestAnimationFrame(animStep);
  });
}

function animStep(ts) {
  const a = anim;
  if (!a) return;
  if (!a.t0) a.t0 = ts;
  const t = ts - a.t0;
  const v = vis[a.idx];

  let acc = 0, leg = a.legs[a.legs.length - 1];
  for (const l of a.legs) {
    if (t < acc + l.dur) { leg = l; break; }
    acc += l.dur;
  }
  const u = leg.dur > 0 ? Math.min(1, Math.max(0, (t - acc) / leg.dur)) : 1;
  const pt = pointAt(leg, leg.len * easeInOut(u));
  v.x = pt.x; v.y = pt.y;
  if (leg.hop) {
    v.lift = Math.sin(Math.PI * u) * CELL * 0.15;
    v.scale = 1 + Math.sin(Math.PI * u) * 0.14;
  } else { v.lift = 0; v.scale = 1; }

  if (t >= a.total) {
    const last = a.legs[a.legs.length - 1];
    const e = pointAt(last, last.len);
    v.x = e.x; v.y = e.y; v.lift = 0; v.scale = 1;
    anim = null; frame(); a.resolve();
    return;
  }
  frame();
  requestAnimationFrame(animStep);
}

function frame() {
  ctx.clearRect(0, 0, CSS, CSS);
  if (staticLayer) ctx.drawImage(staticLayer, 0, 0);

  // spread tokens that share a square
  const groups = new Map();
  tour.roster.forEach((p, i) => {
    const k = p.pos;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(i);
  });
  const off = new Map();
  for (const [, list] of groups) {
    list.forEach((i, n) => {
      const a = (n / Math.max(1, list.length)) * Math.PI * 2 - Math.PI / 2;
      const rad = list.length > 1 ? CELL * 0.15 : 0;
      off.set(i, { dx: Math.cos(a) * rad, dy: Math.sin(a) * rad });
    });
  }

  tour.roster.forEach((p, i) => {
    const v = vis[i];
    if (!v) return;
    const o = off.get(i) || { dx: 0, dy: 0 };
    const x = v.x + o.dx, y = v.y + o.dy - v.lift;
    const r = CELL * 0.21 * v.scale;

    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.65)';
    ctx.shadowBlur = 12; ctx.shadowOffsetY = 4;
    ctx.beginPath(); ctx.arc(x, y + CELL * 0.09, r, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(0,0,0,.4)'; ctx.fill();
    ctx.restore();

    ctx.save();
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.closePath();
    ctx.clip();
    const av = avatars[i];
    if (av) {
      const s = r * 2.15;
      ctx.drawImage(av, x - s / 2, y - s / 2, s, s);
    } else {
      ctx.fillStyle = p.colour; ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
    ctx.restore();

    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.lineWidth = Math.max(2.5, CELL * 0.035);
    ctx.strokeStyle = p.colour; ctx.stroke();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(255,255,255,.45)'; ctx.stroke();

    ctx.beginPath(); ctx.arc(x, y + r * 0.02, r * 0.36, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(8,12,18,.88)'; ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.font = `800 ${Math.round(r * 0.52)}px Inter, system-ui, sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(String(i + 1), x, y + r * 0.05);
  });
}

/* ============================== tournament ============================ */
const tour = {
  roster: [], totalGames: 1, gameIndex: 0,
  points: [], bestRank: [], advance: [],
};
let game = { turn: 0, busy: false, over: false };

/* Interruption safety. `session` is bumped whenever a tournament starts or is
   abandoned; any pending interstitial timer or in-flight animation from an old
   session checks it and bails. Without this, quitting mid-tournament left a
   timer alive that would switch the screen straight back to the board, and a
   throttled background tab could freeze the interstitial on screen forever. */
let session = 0;
let interTimer = null;

function snakeAt(n) { return SNAKES.find((s) => s[0] === n) || null; }
function ladderAt(n) { return LADDERS.find((l) => l[0] === n) || null; }

function currentPlayer() { return tour.roster[game.turn]; }

function startGame(n) {
  tour.gameIndex = n;
  game = { turn: 0, busy: false, over: false };
  tour.roster.forEach((p) => { p.pos = 0; p.finished = false; });
  vis.length = 0;
  tour.roster.forEach(() => {
    const c = centreOf(1);
    vis.push({ x: c.x, y: c.y, lift: 0, scale: 1 });
  });
  tour.roster.forEach((p, i) => { p.active = i === 0; });
  litSnake = null;
  buildStatic();
  $('gameCounter').textContent =
    `Game ${n} of ${tour.totalGames}` + (tour.totalGames > 1 ? ' · tournament' : '');
  $('log').innerHTML = '';
  log(`Game ${n} of ${tour.totalGames} — ${tour.roster.length} player` +
      (tour.roster.length > 1 ? 's' : '') + `.`, '');
  renderPlayers(); renderScorecard(); frame();
}

function beginTournament() {
  if (!tour.roster.length) return;
  showScreen('game');
  buildStatic();
  startGame(1);
}

function finishGame(winnerIdx) {
  const N = tour.roster.length;
  // rank by position, highest first
  const order = tour.roster.map((p, i) => i)
    .sort((a, b) => tour.roster[b].pos - tour.roster[a].pos);
  order.forEach((pi, r) => {
    tour.bestRank[pi] = Math.min(tour.bestRank[pi] ?? 99, r + 1);
  });
  tour.points[winnerIdx] = (tour.points[winnerIdx] || 0) + 1;
  const w = tour.roster[winnerIdx];
  log(`<b>${w.name}</b> wins game ${tour.gameIndex} of ${tour.totalGames}!`, 'win');
  toast(`${w.name} wins game ${tour.gameIndex}!`, 'win');
  game.over = true;
  // roll() returns straight after calling this, so it must clear the lock here.
  // Previously it stayed true forever; startGame()/the lobby happened to reset it,
  // which hid the bug, but the final game goes to showResults() and left the flag
  // permanently wedged.
  game.busy = false;
  renderPlayers();

  const mySession = session;
  setTimeout(async () => {
    if (session !== mySession) return;          // tournament was abandoned
    if (!isGameScreen()) return;                // user navigated away
    if (tour.gameIndex < tour.totalGames) {
      // straight into the next game — the lobby is deliberately NOT shown
      await interstitial(tour.gameIndex + 1);
      if (session !== mySession || !isGameScreen()) return;
      startGame(tour.gameIndex + 1);
    } else {
      showResults();
    }
  }, 1500);
}

function isGameScreen() {
  return $('screenGame').classList.contains('is-active');
}

function interstitial(next) {
  return new Promise((resolve) => {
    const el = $('interstitial');
    $('interTitle').textContent = `Game ${next} of ${tour.totalGames}`;
    $('interSub').textContent = next === tour.totalGames
      ? 'Last game — this one decides it.'
      : 'Next game starting…';
    el.hidden = false;
    clearTimeout(interTimer);
    interTimer = setTimeout(() => { el.hidden = true; interTimer = null; resolve(); }, 1600);
  });
}

function showResults() {
  const N = tour.roster.length;
  const idx = tour.roster.map((_, i) => i).sort((a, b) => {
    const pa = tour.points[a] || 0, pb = tour.points[b] || 0;
    if (pa !== pb) return pb - pa;
    const ra = tour.bestRank[a] ?? 99, rb = tour.bestRank[b] ?? 99;
    if (ra !== rb) return ra - rb;
    return (tour.advance[b] || 0) - (tour.advance[a] || 0);
  });

  const champ = idx[0];
  $('resultsTitle').textContent = tour.totalGames > 1
    ? `Tournament complete — ${tour.totalGames} games`
    : 'Match complete';
  $('winnerKicker').textContent = N === 1 ? 'Solo run finished' : 'Tournament winner';
  $('winnerName').textContent = tour.roster[champ].name;
  $('winnerSub').textContent = N === 1
    ? `Cleared ${tour.totalGames} game${tour.totalGames > 1 ? 's' : ''}.`
    : `${tour.points[champ] || 0} of ${tour.totalGames} games won`;
  $('winnerFace').src = tour.roster[champ].avatar;

  const medals = ['1st', '2nd', '3rd', '4th'];
  $('standings').innerHTML =
    `<thead><tr><th></th><th>Player</th><th style="text-align:right">Won</th>` +
    `<th style="text-align:right">Best</th><th style="text-align:right">Advanced</th></tr></thead><tbody>` +
    idx.map((pi, r) => `
      <tr class="${r === 0 ? 'top' : ''}">
        <td class="medal">${medals[r]}</td>
        <td><div class="who"><img src="${tour.roster[pi].avatar}" alt="" />${tour.roster[pi].name}</div></td>
        <td class="num">${tour.points[pi] || 0}</td>
        <td class="num">${tour.bestRank[pi] ? medals[tour.bestRank[pi] - 1] : '—'}</td>
        <td class="num">${tour.advance[pi] || 0}</td>
      </tr>`).join('') + '</tbody>';

  showScreen('results');
}

/* ------------------------------- a turn -------------------------------- */
function setDie(n) {
  const el = $('dieImg');
  if (dieImgs[n]) el.src = dieImgs[n].src;
  el.alt = 'Dice showing ' + n;
}

async function roll() {
  if (game.busy || game.over) return;
  if (!tour.roster.length) return;
  game.busy = true;
  const mySession = session;
  const alive = () => session === mySession && isGameScreen();
  renderPlayers();

  const me = game.turn;
  const p = currentPlayer();
  const v = 1 + Math.floor(Math.random() * 6);

  const d = $('dieImg');
  d.classList.add('rolling');
  for (let k = 0; k < 8; k++) { setDie(1 + Math.floor(Math.random() * 6)); await sleep(65); }
  d.classList.remove('rolling');
  setDie(v);
  log(`<b>${p.name}</b> rolled <b>${v}</b>`, '');
  await sleep(140);

  const from = p.pos;
  const target = from + v;

  if (target > CELLS) {
    log(`<b>${p.name}</b> needs exactly ${CELLS - from} — stays on ${from}.`, '');
    toast(`Needs exactly ${CELLS - from}`, '');
    await sleep(700);
  } else {
    // one square at a time: step, hop, step, hop…
    const pts = [];
    for (let q = from + 1; q <= target; q++) {
      const c = centreOf(q);
      pts.push({ x: c.x, y: c.y });
    }
    p.pos = target;
    tour.advance[me] = (tour.advance[me] || 0) + v;
    await animateLegs(me, hopLegs(pts));
    if (!alive()) { game.busy = false; return; }
    frame();
    await sleep(200);
    if (!alive()) { game.busy = false; return; }
  }

  // ladder — climb it square by square
  const lad = ladderAt(p.pos);
  if (lad) {
    const pts = [];
    for (let q = p.pos + 1; q <= lad[1]; q++) {
      const c = centreOf(q);
      pts.push({ x: c.x, y: c.y });
    }
    p.pos = lad[1];
    log(`<b>${p.name}</b> climbed the ladder to <b>${lad[1]}</b>`, 'ladder');
    toast(`Ladder → ${lad[1]}`, 'ladder');
    await animateLegs(me, hopLegs(pts));
    if (!alive()) { game.busy = false; return; }
    frame();
    await sleep(420);
    if (!alive()) { game.busy = false; return; }
  }

  // snake — slide down the drawn body
  const snk = snakeAt(p.pos);
  if (snk) {
    const [sFrom, sTo] = snk;
    litSnake = sFrom; buildStatic(); frame();
    // The token rides the exact polyline the body was drawn from, as ONE leg of
    // fixed duration — so the slide is ~0.8s whatever the path length or fps.
    const path = snakePathFor(sFrom, sTo);
    p.pos = sTo;
    log(`<b>${p.name}</b> got bitten on <b>${sFrom}</b> — slid to <b>${sTo}</b>`, 'snake');
    toast(`Snake bite! → ${sTo}`, 'snake');
    await animateLegs(me, [makeLeg(path[0], path.slice(1), TUNING.glideTotalMs, false)]);
    if (!alive()) { game.busy = false; return; }
    litSnake = null; buildStatic(); frame();
    await sleep(420);
    if (!alive()) { game.busy = false; return; }
  }

  if (!alive()) { game.busy = false; return; }
  if (p.pos >= CELLS) { finishGame(me); return; }

  game.turn = (game.turn + 1) % tour.roster.length;
  tour.roster.forEach((q, i) => { q.active = i === game.turn; });
  game.busy = false;
  renderPlayers();
}

/* --------------------------------- UI ---------------------------------- */
function showScreen(which) {
  // Leaving the board tears down anything that could drag us back onto it.
  if (which !== 'game') {
    session += 1;
    clearTimeout(interTimer); interTimer = null;
    const el = $('interstitial'); if (el) el.hidden = true;
    if (anim) { const r = anim.resolve; anim = null; try { r && r(); } catch (_) {} }
    game.busy = false; game.over = false;
    litSnake = null;
  }
  ['Lobby', 'Game', 'Results'].forEach((s) => {
    $('screen' + s).classList.toggle('is-active', s.toLowerCase() === which);
  });
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function renderPlayers() {
  $('players').innerHTML = tour.roster.map((p, i) => `
    <div class="player ${i === 0 ? 'p' + (i + 1) : ''} ${p.active ? 'active' : ''}"
         style="--ring:${p.colour}">
      <img class="face" src="${p.avatar}" alt="" style="--ring:${p.colour}" />
      <span class="name">${p.name}</span>
      <span class="sq">on <b>${p.pos || 1}</b></span>
    </div>`).join('');
  $('turnLine').textContent = game.over ? 'Game over'
    : `${currentPlayer().name} to roll`;
  $('btnRoll').disabled = game.busy || game.over;
}

function renderScorecard() {
  if (tour.totalGames < 2) { $('scorecard').style.display = 'none'; return; }
  $('scorecard').style.display = '';
  $('scorecard').innerHTML =
    `<h2 style="margin:0 0 8px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)">Tournament</h2>` +
    tour.roster.map((p, i) => `
      <div class="row">
        <img class="face" src="${p.avatar}" alt="" />
        <span>${p.name}</span>
        <b>${tour.points[i] || 0} win${(tour.points[i] || 0) === 1 ? '' : 's'}</b>
      </div>`).join('');
}

let toastTimer = null;
function toast(text, kind) {
  const t = $('toast');
  t.textContent = text; t.className = 'toast show ' + (kind || '');
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = 'toast ' + (kind || ''); }, 1400);
}

function log(text, kind) {
  const li = document.createElement('li');
  if (kind) li.className = kind;
  li.innerHTML = text;
  const list = $('log');
  list.prepend(li);
  while (list.children.length > 40) list.lastChild.remove();
}

/* ------------------------------- lobby --------------------------------- */
const selected = new Set([0]);
let chosenGames = 3;

function renderPicker() {
  $('playerPicker').innerHTML = ROSTER.map((p, i) => `
    <button class="pick ${selected.has(i) ? 'is-on' : ''}" data-p="${i}"
            style="--ring:${p.colour}" aria-pressed="${selected.has(i)}">
      <img src="${p.avatar}" alt="${p.name}" />
      <span class="cap">${p.name}</span>
    </button>`).join('');
  $('gamePicker').innerHTML = GAME_OPTIONS.map((n) => `
    <button class="pick ${chosenGames === n ? 'is-on' : ''}" data-g="${n}" aria-pressed="${chosenGames === n}">
      <span class="num">${n}</span><span class="cap">game${n > 1 ? 's' : ''}</span>
    </button>`).join('');
  $('playerCount').textContent = selected.size + ' selected';
  $('gamesHint').textContent = GAME_BLURB[chosenGames];

  $('playerPicker').querySelectorAll('.pick').forEach((b) => {
    b.addEventListener('click', () => {
      const i = +b.dataset.p;
      if (selected.has(i)) { if (selected.size > 1) selected.delete(i); }
      else selected.add(i);
      renderPicker();
    });
  });
  $('gamePicker').querySelectorAll('.pick').forEach((b) => {
    b.addEventListener('click', () => { chosenGames = +b.dataset.g; renderPicker(); });
  });
}

function startFromLobby() {
  const list = [...selected].sort((a, b) => a - b);
  if (!list.length) return;
  if (!img.head || !img.skin || !img.sprite) {
    reportError(new Error('cannot start: assets still loading'), 'startFromLobby');
    return;
  }
  session += 1;                       // any leftover timer from a prior run dies here
  tour.roster = list.map((i) => ({ ...ROSTER[i], pos: 0, active: false, finished: false }));
  tour.totalGames = chosenGames;
  tour.gameIndex = 0;
  tour.points = list.map(() => 0);
  tour.bestRank = list.map(() => null);
  tour.advance = list.map(() => 0);
  game = { turn: 0, busy: false, over: false };
  beginTournament();
}

/* -------------------------------- init --------------------------------- */
const boardProblems = validateBoard();
if (boardProblems.length) {
  console.error('Board rule violations:\n - ' + boardProblems.join('\n - '));
}

loadImages().then(() => {
  const tile = document.createElement('canvas');
  tile.width = 104; tile.height = 56;
  tile.getContext('2d').drawImage(img.skin, 0, 0, 104, 56);
  img.skinPattern = ctx.createPattern(tile, 'repeat');

  renderPicker();
  setDie(1);
  showScreen('lobby');
  if (boardProblems.length) {
    const el = document.createElement('pre');
    el.style.cssText = 'margin:0 0 16px;padding:12px 14px;border-radius:10px;' +
      'background:#2a0d0d;color:#ffb4b4;font:11.5px/1.5 ui-monospace,Menlo,monospace;' +
      'white-space:pre-wrap';
    el.textContent = 'Board rule violations:\n - ' + boardProblems.join('\n - ');
    $('screenLobby').prepend(el);
  }

  $('btnStart').addEventListener('click', startFromLobby);
  $('btnBack').addEventListener('click', () => { showScreen('lobby'); renderPicker(); });
  $('btnQuit').addEventListener('click', () => { showScreen('lobby'); renderPicker(); });
  $('btnRoll').addEventListener('click', roll);
  document.querySelectorAll('.seg-btn').forEach((b) => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.seg-btn').forEach((o) => o.classList.remove('is-active'));
      b.classList.add('is-active');
      mode = b.dataset.mode;
      buildStatic(); frame();
    });
  });

  window.addEventListener('keydown', (e) => {
    if ((e.code === 'Space' || e.key === 'Enter') && $('screenGame').classList.contains('is-active')) {
      e.preventDefault(); roll();
    }
  });
}).catch((err) => { reportError(err, 'init'); });

/* Surface failures instead of dying silently. */
function reportError(err, where) {
  const msg = (err && (err.stack || err.message)) || String(err);
  const box = document.createElement('pre');
  box.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:9999;margin:0;' +
    'padding:12px 16px;background:#2a0d0d;color:#ffb4b4;font:12px/1.5 ui-monospace,' +
    'Menlo,monospace;white-space:pre-wrap;border-bottom:1px solid #6a2b2b';
  box.textContent = 'Snake & Ladder error (' + where + '):\n' + msg;
  document.body.appendChild(box);
  // Beacon only on localhost, where a dev server can log it. On a real host (or
  // file://) this would just be a guaranteed 404 in the console, so skip it.
  const h = location.hostname;
  const local = h === 'localhost' || h === '127.0.0.1' || h === '[::1]';
  if (!local) return;
  try {
    fetch('/__log?where=' + encodeURIComponent(where) + '&msg=' +
          encodeURIComponent(msg.slice(0, 900)));
  } catch (_) { /* offline is fine, the banner already shows it */ }
}

window.addEventListener('error', (e) => reportError(e.error || e.message, 'window.onerror'));
window.addEventListener('unhandledrejection', (e) => reportError(e.reason, 'unhandledrejection'));
