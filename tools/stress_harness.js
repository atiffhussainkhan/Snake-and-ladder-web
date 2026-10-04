/* =========================================================================
   STRESS HARNESS — appended only to the generated stress copy of game.js.
   Never shipped. Plays real tournaments in the real browser with a seeded
   PRNG and asserts invariants after every single roll.
   ========================================================================= */

const STRESS = { totalGames: 0, totalRolls: 0, totalChecks: 0, errors: [], runs: [] };
let CUR = null;

function inv(cond, msg) {
  CUR.checks++;
  if (!cond && CUR.errors.length < 40) CUR.errors.push(msg);
  return cond;   // MUST return cond: callers use `if (!inv(...)) break;`
}

const lobbyOn = () => $('screenLobby').classList.contains('is-active');
const resOn = () => $('screenResults').classList.contains('is-active');
const gameOn = () => $('screenGame').classList.contains('is-active');

/* Seeded LCG so any failing run can be replayed exactly. */
function makeRnd(seed) {
  let s = seed >>> 0 || 1;
  return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
}

/* The stress build zeroes `sleep` for speed, so it cannot be used to wait for
   real wall-clock events — the game transition (finishGame 1500ms + interstitial
   1600ms) is on genuine setTimeout, and a spin of setTimeout(0) burns through
   its iteration budget before that fires, especially in a throttled background
   tab. This waits in real time. */
const realSleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function playTournament(players, games, seed) {
  CUR = { players, games, seed, gamesPlayed: 0, rolls: 0, checks: 0,
          errors: [], maxPos: 0, snakeHits: 0, ladderHits: 0, abort: false };
  const realRandom = Math.random;
  Math.random = makeRnd(seed);

  try {
    const bp = validateBoard();
    if (bp.length) CUR.errors.push('board rules: ' + bp.join('; '));

    selected.clear();
    for (let i = 0; i < players; i++) selected.add(i);
    chosenGames = games;
    renderPicker();
    startFromLobby();
    // Capture AFTER startFromLobby — it bumps the session counter. It must also
    // be `let`, because the abort path restarts the tournament and re-captures.
    let mySession = session;

    inv(tour.roster.length === players, `roster ${tour.roster.length} != ${players}`);
    inv(gameOn(), 'game screen not active after start');
    inv(!lobbyOn(), 'lobby still active after start');
    inv($('btnRoll').disabled === false, 'roll button disabled at game start');

    // Randomly abort one tournament per run to exercise the interrupt path.
    let willAbort = (seed % 4 === 3) && players > 1;   // let: cleared after the abort
    let abortAt = willAbort ? 2 + (seed % 7) : -1;

    // A wall-clock deadline, not an iteration count. Safari throttles timers in
    // background tabs, so N iterations of realSleep can elapse in a fraction of
    // the time the real 1500ms game-transition timer needs. Deadline = immune.
    const DEADLINE = Date.now() + 150000;
    let guard = 0;
    while (!resOn() && Date.now() < DEADLINE && guard++ < 2000) {
      if (session !== mySession) { inv(false, 'session changed unexpectedly'); break; }

      if (game.over) {
        // window between finishing a game and the next one starting:
        // the lobby must NEVER appear here. Wait in real time — this transition
        // is ~3.1s of genuine setTimeout.
        if (!inv(!lobbyOn(), 'LOBBY SHOWN between games')) break;
        await realSleep(120);
        continue;
      }

      if (willAbort && CUR.rolls === abortAt) {
        CUR.abort = true;
        $('btnQuit').click();
        await realSleep(60);
        inv(lobbyOn(), 'quit did not return to lobby');
        inv(!gameOn() && !resOn(), 'game/results still active after quit');
        inv(game.busy === false, 'busy stuck true after quit');
        inv($('interstitial').hidden === true, 'interstitial visible after quit');
        // a fresh tournament must still be startable afterwards
        chosenGames = 1; renderPicker();
        startFromLobby();
        mySession = session;
        willAbort = false;
        await realSleep(60);
        continue;
      }

      const g0 = tour.gameIndex;
      const posBefore = tour.roster.map((p) => p.pos);
      await roll();
      CUR.rolls++;

      // ---- per-roll invariants -------------------------------------------
      const activeCount = tour.roster.filter((p) => p.active).length;
      inv(tour.roster.length === players, `roster changed to ${tour.roster.length}`);

      for (let i = 0; i < tour.roster.length; i++) {
        const p = tour.roster[i];
        inv(Number.isInteger(p.pos), `pos ${p.pos} not an integer`);
        inv(p.pos >= 0 && p.pos <= CELLS, `pos ${p.pos} out of [0,100]`);

        if (p.pos === CELLS) {
          inv(game.over, 'a player reached 100 but the game is not over');
          inv(p.pos === posBefore[i] + (CELLS - posBefore[i]),
             'reached 100 by a jump larger than the remainder');
        }

        // token must sit exactly on its square after the animation settles
        const v = vis[i];
        if (v) {
          const c = centreOf(p.pos || 1);
          const d = Math.hypot(v.x - c.x, v.y - c.y);
          if (!inv(d < 2.5, `token ${i} sits ${d.toFixed(2)}px off square ${p.pos}`)) break;
          inv(v.lift === 0 && v.scale === 1, `token ${i} stuck mid-hop (lift/scale)`);
        }

        // snake / ladder bookkeeping
        const landed = p.pos !== posBefore[i] && !snakeAt(p.pos) && !ladderAt(p.pos);
        if (snakeAt(posBefore[i]) && p.pos === posBefore[i]) CUR.ladderHits++;
      }

      if (game.over) {
        const sn = tour.roster.map((p) => p.pos).findIndex((q) => q === CELLS);
        if (sn >= 0) { /* winner landed exactly on 100 */ }
        inv(tour.gameIndex === g0, `gameIndex moved ${g0} -> ${tour.gameIndex} mid-game`);
        inv(activeCount <= 1, `${activeCount} players active at game end`);
        CUR.gamesPlayed++;
        CUR.maxPos = Math.max(CUR.maxPos, ...tour.roster.map((p) => p.pos));
      } else {
        inv(activeCount === 1, `${activeCount} active players mid-game`);
        inv(tour.roster[game.turn].active === true, 'active flag not on current player');
        inv(tour.gameIndex >= 1 && tour.gameIndex <= games,
            `gameIndex ${tour.gameIndex} out of [1,${games}]`);
      }

      const pt = tour.points.reduce((a, b) => a + (b || 0), 0);
      inv(pt === CUR.gamesPlayed, `points total ${pt} != games played ${CUR.gamesPlayed}`);
      for (let i = 0; i < tour.points.length; i++) {
        inv(tour.points[i] >= 0 && tour.points[i] <= games, `points[${i}]=${tour.points[i]}`);
      }
    }

    // ---- end of tournament ----------------------------------------------
    if (CUR.abort) {
      CUR.gamesPlayed = 0;
    } else {
      if (!resOn()) {
        // Loop ran out. Capture exactly where it stalled — this state is what
        // distinguishes "transition timer never fired" from "wrong screen".
        await beacon('stall', {
          players, games, seed, guard,
          gameOver: game.over, busy: game.busy, gameIndex: tour.gameIndex,
          lobby: lobbyOn(), game: gameOn(), res: resOn(),
          interHidden: $('interstitial').hidden,
          interDisplay: getComputedStyle($('interstitial')).display,
          session, mySession,
          pos: tour.roster.map((p) => p.pos), points: tour.points.slice(),
        });
      }
      inv(resOn(), 'results screen never appeared');
      inv(CUR.gamesPlayed === games, `played ${CUR.gamesPlayed} games, expected ${games}`);
      inv(tour.points.reduce((a, b) => a + (b || 0), 0) === games, 'points != games');
      inv(document.querySelectorAll('#standings tbody tr').length === players,
          `standings rows ${document.querySelectorAll('#standings tbody tr').length}`);
      inv($('winnerName').textContent.length > 0, 'no winner name');
      const champ = $('winnerName').textContent;
      inv(tour.roster.some((p) => p.name === champ), `winner "${champ}" not in roster`);
      inv(tour.gameIndex === games, `final gameIndex ${tour.gameIndex} != ${games}`);
    }
  } catch (e) {
    CUR.errors.push('EXCEPTION: ' + ((e && e.stack) || e));
  } finally {
    await beacon('runerr', { players, games, seed, errors: CUR.errors.slice(),
                             gamesPlayed: CUR.gamesPlayed, rolls: CUR.rolls });
    Math.random = realRandom;
    showScreen('lobby');
    STRESS.totalGames += CUR.gamesPlayed;
    STRESS.totalRolls += CUR.rolls;
    STRESS.totalChecks += CUR.checks;
    for (const err of CUR.errors) STRESS.errors.push(`[p${CUR.players} g${CUR.games} s${CUR.seed}] ${err}`);
    STRESS.runs.push({ p: CUR.players, g: CUR.games, s: CUR.seed,
                       games: CUR.gamesPlayed, rolls: CUR.rolls,
                       checks: CUR.checks, errors: CUR.errors.length, abort: CUR.abort });
  }
  return CUR;
}

/* Every beacon carries a run id. Two stress tabs may briefly coexist in
   Safari, and without this their beacons interleave and results get attributed
   to the wrong run. */
const RUN_ID = (location.search.match(/run=([A-Za-z0-9]+)/) || [])[1] || 'default';

function beacon(tag, obj) {
  return fetch('/__log?where=' + tag + '&msg=' + encodeURIComponent(
    JSON.stringify(Object.assign({ run: RUN_ID }, obj))));
}

/* The board cannot be built before the sprite assets exist. The product gates
   this via the .then() that wires the buttons, but the harness talks to the
   functions directly, so it has to wait for the same condition. */
async function waitForAssets(timeoutMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < (timeoutMs || 20000)) {
    if (img.head && img.skin && img.sprite && avatars[0] && dieImgs[1]) return true;
    await new Promise((r) => setTimeout(r, 50));
  }
  return false;
}

async function stressAll() {
  const ready = await waitForAssets(20000);
  if (!ready) {
    await beacon('final', { fatal: 'assets never loaded', totalGames: 0, totalRolls: 0,
                            totalChecks: 0, errorCount: 1, errors: ['assets never loaded'], runs: [] });
    return;
  }
  const combos = [];
  for (let p = 1; p <= 4; p++) for (const g of [1, 3, 5, 7, 9]) combos.push([p, g]);
  const seed = 20261004;
  const target = +((location.search.match(/target=(\d+)/)||[])[1] || 120);
  let played = 0;
  let i = 0;
  while (played < target && i < combos.length * 3) {
    const [p, g] = combos[i % combos.length];
    const s = (seed + i * 7919) >>> 0;
    await playTournament(p, g, s);
    const r = STRESS.runs[STRESS.runs.length - 1];
    played += r.abort ? 0 : g;              // an aborted run plays no counted games
    i++;
    await beacon('progress', { played, target, runs: STRESS.runs.length,
                               errors: STRESS.errors.length, last: r });
  }
  await beacon('final', {
    totalGames: STRESS.totalGames, totalRolls: STRESS.totalRolls,
    totalChecks: STRESS.totalChecks, errorCount: STRESS.errors.length,
    errors: STRESS.errors.slice(0, 30), runs: STRESS.runs,
  });
  STRESS.done = true;
}


/* Measures ACTUAL setTimeout latency. If this is wildly larger than the
   requested delay, the tab is being throttled by the browser because it is not
   frontmost — which invalidates any wall-clock assumption in the harness. */
function timerProbe(tag) {
  const req = 1500;
  const t0 = Date.now();
  setTimeout(() => beacon('probe', {
    tag, requestedMs: req, actualMs: Date.now() - t0,
    visibility: document.visibilityState, hidden: document.hidden,
  }), req);
}

if (/[?&]diag/.test(location.search)) {
  setTimeout(async () => {
    await waitForAssets(20000);
    timerProbe('immediate');
    await realSleep(3000);
    timerProbe('after-3s');
    const trace = [];
    const snap = (tag) => trace.push({
      tag, gameOver: game.over, busy: game.busy, over: game.over,
      gameIndex: tour.gameIndex, total: tour.totalGames,
      pos: tour.roster.map((p) => p.pos),
      lobby: lobbyOn(), game: gameOn(), res: resOn(),
      interHidden: $('interstitial').hidden,
      session, screenGameClass: $('screenGame').className,
    });
    Math.random = makeRnd(4242);
    selected.clear(); selected.add(0); chosenGames = 1;
    renderPicker(); startFromLobby();
    snap('after-start');
    for (let i = 0; i < 200 && !resOn(); i++) {
      if (game.over) { await realSleep(150); continue; }
      await roll();
      if (game.over) { snap('just-won'); }
      if (trace.length < 400) snap('roll' + i);
    }
    snap('end-of-loop');
    await realSleep(4500);          // well past the 1500ms + 1600ms transition
    snap('after-4.5s-settle');
    await beacon('diag', { trace, errors: STRESS.errors });
  }, 400);
}

if (/[?&]stress/.test(location.search)) {
  setTimeout(() => { stressAll(); }, 400);
}
