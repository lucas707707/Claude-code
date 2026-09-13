(() => {
  'use strict';

  // ---------- Setup ----------
  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d');
  const TILE = 40;
  const COLS = canvas.width / TILE; // 12
  const ANCHOR_Y = canvas.height - 3 * TILE; // player's screen anchor (top-left of its tile)

  const scoreEl = document.getElementById('score');
  const bestEl = document.getElementById('best');
  const startScreen = document.getElementById('start-screen');
  const gameoverScreen = document.getElementById('gameover-screen');
  const finalScoreEl = document.getElementById('final-score');
  const bestScoreEl = document.getElementById('best-score');
  const startBtn = document.getElementById('start-btn');
  const restartBtn = document.getElementById('restart-btn');
  const touchControls = document.getElementById('touch-controls');

  const BEST_KEY = 'crossyRoadBest';
  let best = parseInt(localStorage.getItem(BEST_KEY) || '0', 10);
  bestEl.textContent = 'Best: ' + best;

  // ---------- State ----------
  let state = 'start'; // 'start' | 'playing' | 'gameover'
  let score = 0;
  let lanes = new Map(); // row -> lane data
  let camera = { y: 0 };
  let time = 0;

  const MOVE_DURATION = 0.13; // seconds

  const player = {
    col: Math.floor(COLS / 2),
    row: 0,
    x: 0, y: 0,           // world pixel (top-left of current tile), used while resting
    fromX: 0, fromY: 0,
    toX: 0, toY: 0,
    moveT: 1,              // 1 = not moving
    facing: 0,              // degrees, for sprite rotation
    alive: true,
    squish: 1,
  };

  function worldY(row) { return -row * TILE; }

  function resetPlayer() {
    player.col = Math.floor(COLS / 2);
    player.row = 0;
    player.x = player.col * TILE;
    player.y = worldY(player.row);
    player.fromX = player.toX = player.x;
    player.fromY = player.toY = player.y;
    player.moveT = 1;
    player.facing = 0;
    player.alive = true;
    player.squish = 1;
  }

  // ---------- Lane generation ----------
  const CAR_COLORS = ['#e94f4f', '#f2a541', '#4f8ef2', '#7bd389', '#c77dff', '#f2f2f2'];

  function difficultyMult(row) {
    return Math.min(1 + row / 90, 2.3);
  }

  function makeGrassLane(row) {
    const lane = { type: 'grass', trees: new Set() };
    if (row >= 2) {
      const treeCount = Math.floor(Math.random() * 4); // 0-3
      const cols = shuffledCols();
      let placed = 0;
      for (const c of cols) {
        if (placed >= treeCount) break;
        // never block the column player currently occupies on the safe start
        lane.trees.add(c);
        placed++;
      }
      // guarantee at least half the lane passable
      if (lane.trees.size > COLS - 6) {
        const arr = Array.from(lane.trees);
        while (lane.trees.size > COLS - 6) lane.trees.delete(arr.pop());
      }
    }
    return lane;
  }

  function shuffledCols() {
    const arr = Array.from({ length: COLS }, (_, i) => i);
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  function makeRoadLane(row) {
    const dir = Math.random() < 0.5 ? -1 : 1;
    const mult = difficultyMult(row);
    const speed = (55 + Math.random() * 55) * mult; // px/sec
    const vehicles = [];
    let x = Math.random() * TILE * 3;
    const laneSpan = COLS * TILE;
    while (x < laneSpan) {
      const isTruck = Math.random() < 0.22;
      const width = isTruck ? 2 : 1;
      vehicles.push({
        x,
        width,
        color: CAR_COLORS[Math.floor(Math.random() * CAR_COLORS.length)],
      });
      x += width * TILE + TILE * (1.4 + Math.random() * 1.8);
    }
    return { type: 'road', dir, speed, vehicles, laneSpan };
  }

  function makeWaterLane(row) {
    const dir = Math.random() < 0.5 ? -1 : 1;
    const mult = difficultyMult(row);
    const speed = (35 + Math.random() * 40) * mult;
    const logs = [];
    let x = Math.random() * TILE * 2;
    const laneSpan = COLS * TILE;
    while (x < laneSpan) {
      const width = 2 + Math.floor(Math.random() * 3); // 2-4
      logs.push({ x, width });
      x += width * TILE + TILE * (0.6 + Math.random() * 1.3);
    }
    // make sure lane isn't fully empty
    if (logs.length === 0) logs.push({ x: 0, width: 3 });
    return { type: 'water', dir, speed, logs, laneSpan };
  }

  let lastTypes = ['grass', 'grass'];

  function pickType(row) {
    if (row < 2) return 'grass';
    const weights = { grass: 0.42, road: 0.35, water: 0.23 };
    // avoid 3 of the same hazard type in a row
    if (lastTypes[0] === lastTypes[1] && lastTypes[1] !== 'grass') {
      weights[lastTypes[1]] = 0;
    }
    const total = weights.grass + weights.road + weights.water;
    let r = Math.random() * total;
    for (const t of ['grass', 'road', 'water']) {
      if (r < weights[t]) return t;
      r -= weights[t];
    }
    return 'grass';
  }

  function generateLane(row) {
    if (lanes.has(row)) return lanes.get(row);
    const type = pickType(row);
    lastTypes.push(type);
    if (lastTypes.length > 2) lastTypes.shift();
    let lane;
    if (type === 'road') lane = makeRoadLane(row);
    else if (type === 'water') lane = makeWaterLane(row);
    else lane = makeGrassLane(row);
    lanes.set(row, lane);
    return lane;
  }

  function ensureLanesAround(row) {
    for (let r = Math.max(0, row - 8); r <= row + 24; r++) generateLane(r);
    // prune far-behind lanes
    for (const r of lanes.keys()) {
      if (r < row - 12) lanes.delete(r);
    }
  }

  // ---------- Input ----------
  function tryMove(dc, dr) {
    if (state !== 'playing' || !player.alive) return;
    if (player.moveT < 1) return; // still animating

    const targetCol = player.col + dc;
    const targetRow = Math.max(0, player.row + dr);
    if (targetCol < 0 || targetCol >= COLS) return;
    if (targetCol === player.col && targetRow === player.row) return;

    ensureLanesAround(targetRow);
    const targetLane = lanes.get(targetRow);
    if (targetLane && targetLane.type === 'grass' && targetLane.trees.has(targetCol)) return;

    player.fromX = player.x;
    player.fromY = player.y;
    player.toX = targetCol * TILE;
    player.toY = worldY(targetRow);
    player.moveT = 0;
    player.col = targetCol;
    player.row = targetRow;
    if (dr > 0) player.facing = 0;
    else if (dr < 0) player.facing = 180;
    else if (dc > 0) player.facing = 90;
    else if (dc < 0) player.facing = 270;

    if (player.row > score) {
      score = player.row;
      scoreEl.textContent = score;
    }
  }

  const KEY_MAP = {
    ArrowUp: [0, 1], w: [0, 1], W: [0, 1],
    ArrowDown: [0, -1], s: [0, -1], S: [0, -1],
    ArrowLeft: [-1, 0], a: [-1, 0], A: [-1, 0],
    ArrowRight: [1, 0], d: [1, 0], D: [1, 0],
  };

  window.addEventListener('keydown', (e) => {
    if (state === 'start' && (e.key === 'Enter' || e.key === ' ' || KEY_MAP[e.key])) {
      e.preventDefault();
      beginGame();
      return;
    }
    if (state === 'gameover' && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      beginGame();
      return;
    }
    const mv = KEY_MAP[e.key];
    if (mv) {
      e.preventDefault();
      tryMove(mv[0], mv[1]);
    }
  });

  touchControls.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const dir = btn.dataset.dir;
      if (dir === 'up') tryMove(0, 1);
      if (dir === 'down') tryMove(0, -1);
      if (dir === 'left') tryMove(-1, 0);
      if (dir === 'right') tryMove(1, 0);
    });
  });

  // swipe support directly on canvas
  let touchStart = null;
  canvas.addEventListener('touchstart', (e) => {
    const t = e.changedTouches[0];
    touchStart = { x: t.clientX, y: t.clientY };
  }, { passive: true });
  canvas.addEventListener('touchend', (e) => {
    if (!touchStart) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - touchStart.x;
    const dy = t.clientY - touchStart.y;
    const absX = Math.abs(dx), absY = Math.abs(dy);
    const THRESH = 24;
    if (Math.max(absX, absY) > THRESH) {
      if (absX > absY) tryMove(dx > 0 ? 1 : -1, 0);
      else tryMove(0, dy > 0 ? -1 : 1);
    } else if (state !== 'playing') {
      beginGame();
    }
    touchStart = null;
  }, { passive: true });

  startBtn.addEventListener('click', beginGame);
  restartBtn.addEventListener('click', beginGame);

  function beginGame() {
    lanes.clear();
    lastTypes = ['grass', 'grass'];
    score = 0;
    scoreEl.textContent = '0';
    resetPlayer();
    ensureLanesAround(0);
    camera.y = player.y - ANCHOR_Y + ANCHOR_Y; // = player.y
    camera.y = player.y;
    state = 'playing';
    startScreen.classList.add('hidden');
    gameoverScreen.classList.add('hidden');
  }

  function endGame() {
    state = 'gameover';
    player.alive = false;
    if (score > best) {
      best = score;
      localStorage.setItem(BEST_KEY, String(best));
    }
    finalScoreEl.textContent = 'Score: ' + score;
    bestScoreEl.textContent = 'Best: ' + best;
    bestEl.textContent = 'Best: ' + best;
    setTimeout(() => gameoverScreen.classList.remove('hidden'), 350);
  }

  // ---------- Update ----------
  function updateLaneObstacles(row, lane, dt) {
    const list = lane.type === 'road' ? lane.vehicles : lane.type === 'water' ? lane.logs : null;
    if (!list) return;
    const speed = lane.speed * lane.dir;
    for (const obj of list) {
      obj.x += speed * dt;
      if (lane.dir > 0 && obj.x > lane.laneSpan + TILE) obj.x -= lane.laneSpan + TILE * 4;
      if (lane.dir < 0 && obj.x < -obj.width * TILE - TILE * 3) obj.x += lane.laneSpan + TILE * 4;
    }
  }

  function updatePlayer(dt) {
    if (player.moveT < 1) {
      player.moveT = Math.min(1, player.moveT + dt / MOVE_DURATION);
      const t = player.moveT;
      const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      player.x = player.fromX + (player.toX - player.fromX) * ease;
      player.y = player.fromY + (player.toY - player.fromY) * ease;
      player.squish = 1 - Math.sin(t * Math.PI) * 0.22;
      if (player.moveT >= 1) {
        player.x = player.toX;
        player.y = player.toY;
        player.squish = 1;
      }
      return; // no hazard checks mid-jump
    }

    const lane = lanes.get(player.row);
    if (!lane) return;

    if (lane.type === 'water') {
      let onLog = null;
      const px = player.x + TILE / 2;
      for (const log of lane.logs) {
        if (px >= log.x && px <= log.x + log.width * TILE) { onLog = log; break; }
      }
      if (onLog) {
        const drift = lane.speed * lane.dir * dt;
        player.x += drift;
        player.toX = player.x;
        player.fromX = player.x;
        if (player.x < -TILE * 0.6 || player.x > COLS * TILE - TILE * 0.4) {
          endGame();
        }
      } else {
        endGame();
      }
    } else if (lane.type === 'road') {
      const pad = 6;
      const pLeft = player.x + pad, pRight = player.x + TILE - pad;
      for (const v of lane.vehicles) {
        const vLeft = v.x, vRight = v.x + v.width * TILE;
        if (pRight > vLeft && pLeft < vRight) { endGame(); break; }
      }
    }
  }

  function update(dt) {
    if (state !== 'playing') return;
    ensureLanesAround(player.row);
    for (const [row, lane] of lanes) updateLaneObstacles(row, lane, dt);
    updatePlayer(dt);
    camera.y += (player.y - camera.y) * Math.min(1, dt * 8);
  }

  // ---------- Draw ----------
  function screenY(wy) { return wy - camera.y + ANCHOR_Y; }

  function drawLaneBackground(row, lane, sy) {
    if (sy < -TILE || sy > canvas.height + TILE) return;
    if (lane.type === 'grass') {
      ctx.fillStyle = row % 2 === 0 ? '#7ec850' : '#74bd48';
    } else if (lane.type === 'road') {
      ctx.fillStyle = '#3a3b3c';
    } else {
      ctx.fillStyle = row % 2 === 0 ? '#4aa8d8' : '#45a0d0';
    }
    ctx.fillRect(0, sy, canvas.width, TILE);

    if (lane.type === 'road') {
      ctx.strokeStyle = 'rgba(255,255,255,0.55)';
      ctx.lineWidth = 3;
      ctx.setLineDash([14, 12]);
      ctx.beginPath();
      ctx.moveTo(0, sy + TILE / 2);
      ctx.lineTo(canvas.width, sy + TILE / 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    if (lane.type === 'water') {
      ctx.strokeStyle = 'rgba(255,255,255,0.25)';
      ctx.lineWidth = 2;
      for (let i = 0; i < 3; i++) {
        const wave = Math.sin(time * 2 + row * 1.3 + i * 2) * 4;
        ctx.beginPath();
        ctx.moveTo(0, sy + 10 + i * 10 + wave);
        ctx.lineTo(canvas.width, sy + 10 + i * 10 + wave);
        ctx.stroke();
      }
    }
  }

  function drawTree(cx, cy) {
    ctx.fillStyle = '#7a4a2b';
    ctx.fillRect(cx - 4, cy + 4, 8, 12);
    ctx.fillStyle = '#3f8f3f';
    ctx.beginPath(); ctx.arc(cx, cy - 6, 14, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#4fae4f';
    ctx.beginPath(); ctx.arc(cx - 6, cy - 2, 9, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(cx + 7, cy - 1, 9, 0, Math.PI * 2); ctx.fill();
  }

  function drawCar(x, sy, width, color, dir) {
    const w = width * TILE - 8, h = TILE - 12;
    const cx = x + 4, cyTop = sy + 6;
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,0.35)';
    ctx.shadowBlur = 4;
    ctx.shadowOffsetY = 3;
    roundRect(cx, cyTop, w, h, 6);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.restore();

    ctx.fillStyle = 'rgba(255,255,255,0.75)';
    const winW = w * 0.32;
    if (dir > 0) roundRect(cx + w - winW - 6, cyTop + 4, winW, h - 8, 3);
    else roundRect(cx + 6, cyTop + 4, winW, h - 8, 3);
    ctx.fill();

    ctx.fillStyle = '#222';
    ctx.beginPath(); ctx.arc(cx + 8, cyTop + h, 4, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(cx + w - 8, cyTop + h, 4, 0, Math.PI * 2); ctx.fill();
  }

  function drawLog(x, sy, width) {
    const w = width * TILE - 6, h = TILE - 14;
    const cx = x + 3, cy = sy + 7;
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,0.25)';
    ctx.shadowBlur = 3;
    ctx.shadowOffsetY = 2;
    roundRect(cx, cy, w, h, h / 2);
    ctx.fillStyle = '#a9713f';
    ctx.fill();
    ctx.restore();
    ctx.strokeStyle = 'rgba(0,0,0,0.18)';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx + 8, cy + h / 2, h / 2 - 3, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(cx + w - 8, cy + h / 2, h / 2 - 3, 0, Math.PI * 2); ctx.stroke();
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawPlayer() {
    const cx = player.x + TILE / 2;
    const cy = screenY(player.y) + TILE / 2;
    const jumpLift = Math.sin(player.moveT * Math.PI) * 8;

    ctx.save();
    ctx.translate(cx, cy - jumpLift);
    const scaleY = player.squish;
    const scaleX = 2 - scaleY;

    // shadow
    ctx.fillStyle = 'rgba(0,0,0,0.25)';
    ctx.beginPath();
    ctx.ellipse(0, jumpLift + TILE / 2 - 4, 12 * (2 - scaleX + 1) / 2, 5, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.scale(scaleX, scaleY);

    // legs
    ctx.fillStyle = '#e8a23d';
    ctx.fillRect(-7, 9, 4, 6);
    ctx.fillRect(3, 9, 4, 6);

    // body
    ctx.fillStyle = '#ffd23f';
    ctx.beginPath(); ctx.arc(0, 0, 13, 0, Math.PI * 2); ctx.fill();

    // comb
    ctx.fillStyle = '#e94f4f';
    ctx.beginPath(); ctx.arc(-3, -14, 3.5, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(3, -15, 3.5, 0, Math.PI * 2); ctx.fill();

    // beak (points in facing direction)
    ctx.save();
    ctx.rotate((player.facing * Math.PI) / 180);
    ctx.fillStyle = '#f28a1e';
    ctx.beginPath();
    ctx.moveTo(6, -3);
    ctx.lineTo(15, 0);
    ctx.lineTo(6, 3);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // eyes
    ctx.fillStyle = '#2a2a2a';
    ctx.beginPath(); ctx.arc(-5, -3, 2.2, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(5, -3, 2.2, 0, Math.PI * 2); ctx.fill();

    ctx.restore();
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const centerRow = Math.round(player.row);
    for (let r = centerRow - 8; r <= centerRow + 24; r++) {
      const lane = lanes.get(r);
      if (!lane) continue;
      const sy = screenY(worldY(r));
      drawLaneBackground(r, lane, sy);
    }

    for (let r = centerRow - 8; r <= centerRow + 24; r++) {
      const lane = lanes.get(r);
      if (!lane) continue;
      const sy = screenY(worldY(r));
      if (sy < -TILE || sy > canvas.height + TILE) continue;

      if (lane.type === 'grass') {
        for (const c of lane.trees) drawTree(c * TILE + TILE / 2, sy + TILE / 2);
      } else if (lane.type === 'road') {
        for (const v of lane.vehicles) drawCar(v.x, sy, v.width, v.color, lane.dir);
      } else if (lane.type === 'water') {
        for (const log of lane.logs) drawLog(log.x, sy, log.width);
      }
    }

    if (state !== 'start') drawPlayer();
  }

  // ---------- Loop ----------
  let lastT = performance.now();
  function loop(now) {
    const dt = Math.min(0.05, (now - lastT) / 1000);
    lastT = now;
    time += dt;
    update(dt);
    draw();
    requestAnimationFrame(loop);
  }

  resetPlayer();
  ensureLanesAround(0);
  camera.y = player.y;
  requestAnimationFrame(loop);
})();
