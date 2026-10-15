let socket;
let connection = "connecting";
let pose = { detected: false, lean: 0, arms_spread: false, crouch: false, confidence: 0 };
let bubbles = [];
let fish = [];
let dolphinX = 0.5;
let dolphinY = 0.52;
let targetX = 0.5;
let ringCooldown = 0;
let deepMix = 0;
let lastRing = false;
let frameCountSafe = 0;

function setup() {
  const c = createCanvas(1100, 620);
  c.parent("canvas-holder");
  colorMode(HSB, 360, 100, 100, 100);
  for (let i = 0; i < 45; i++) bubbles.push(makeBubble(random(width), random(height)));
  for (let i = 0; i < 12; i++) fish.push({ x: random(width), y: random(height * 0.2, height * 0.85), speed: random(0.5, 2.2), size: random(9, 18), phase: random(TWO_PI) });
  connectSocket();
}

function connectSocket() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(scheme + "://" + location.host + "/ws");
  socket.onopen = () => { connection = "connected"; updateStatus(); };
  socket.onmessage = (event) => {
    try {
      const next = JSON.parse(event.data);
      pose = next;
      if (next.detected) {
        targetX = constrain(0.5 + next.lean * 0.43, 0.05, 0.95);
        if (next.arms_spread && !lastRing && ringCooldown <= 0) {
          burstRing();
          ringCooldown = 35;
        }
        lastRing = !!next.arms_spread;
      } else {
        lastRing = false;
      }
      updateStatus();
    } catch (_) {}
  };
  socket.onclose = () => { connection = "disconnected"; updateStatus(); setTimeout(connectSocket, 1500); };
  socket.onerror = () => { connection = "error"; updateStatus(); };
}

function updateStatus() {
  const el = document.getElementById("status");
  if (!el) return;
  const ok = connection === "connected" && pose.camera === "ready";
  const label = connection !== "connected" ? "WebSocket 再接続中…" :
    pose.camera === "unavailable" ? "カメラが見つかりません" :
    pose.camera === "error" ? "MediaPipe エラー（ターミナルを確認）" :
    !pose.detected ? "カメラ接続済み · 全身を映してください" :
    "姿勢を検出中 · " + Math.round((pose.confidence || 0) * 100) + "%";
  el.innerHTML = '<span class="dot ' + (ok ? "ok" : "") + '"></span>' + label;
}

function makeBubble(x, y) {
  return { x, y, r: random(2, 8), speed: random(0.5, 2.0), drift: random(-0.4, 0.4), alpha: random(35, 85) };
}

function burstRing() {
  const cx = dolphinX * width;
  const cy = dolphinY * height;
  for (let i = 0; i < 38; i++) {
    const a = TWO_PI * i / 38;
    bubbles.push({ x: cx, y: cy, r: random(3, 7), speed: random(1.4, 3.3), drift: cos(a) * 2.5, vy: sin(a) * 2.5, alpha: 90, ring: true, life: 48 });
  }
}

function draw() {
  frameCountSafe++;
  if (ringCooldown > 0) ringCooldown--;
  deepMix = lerp(deepMix, pose.detected && pose.crouch ? 1 : 0, 0.045);
  drawOcean();
  drawLightRays();
  drawCoral();
  updateFish();
  updateBubbles();
  dolphinX = lerp(dolphinX, targetX, 0.075);
  dolphinY = lerp(dolphinY, pose.detected && pose.crouch ? 0.68 : 0.52, 0.04);
  drawDolphin(dolphinX * width, dolphinY * height);
  drawHUD();
}

function drawOcean() {
  const topHue = lerp(202, 228, deepMix);
  for (let y = 0; y < height; y += 4) {
    const t = y / height;
    noStroke();
    fill(lerp(topHue, 222, t), lerp(78, 94, t), lerp(38, 8, t), 100);
    rect(0, y, width, 5);
  }
  noStroke();
  fill(185, 80, 80, 5 + 7 * sin(frameCountSafe * 0.02));
  ellipse(width * 0.22, height * 0.2, width * 0.6, height * 0.4);
}

function drawLightRays() {
  push();
  stroke(180, 30, 100, 7 * (1 - deepMix));
  strokeWeight(24);
  for (let i = 0; i < 7; i++) {
    const x = width * (i / 6) + sin(frameCountSafe * 0.008 + i) * 35;
    line(x, 0, x - 90, height * 0.85);
  }
  pop();
}

function drawCoral() {
  push();
  noStroke();
  fill(330, 75, 50, 75);
  for (let i = 0; i < 10; i++) {
    const x = width * i / 9;
    const h = 25 + 22 * sin(i * 2.2);
    ellipse(x, height - 10, 32, h);
    rect(x - 5, height - h, 10, h);
    ellipse(x - 12, height - h, 14, 25);
    ellipse(x + 12, height - h - 9, 14, 30);
  }
  pop();
}

function updateFish() {
  for (const f of fish) {
    f.x += f.speed * (pose.detected && pose.arms_spread ? 1.7 : 1);
    f.y += sin(frameCountSafe * 0.035 + f.phase) * 0.45;
    if (f.x > width + 30) { f.x = -25; f.y = random(height * 0.2, height * 0.8); }
    push();
    translate(f.x, f.y);
    scale(-1, 1);
    noStroke();
    fill(lerp(42, 185, deepMix), 65, 95, 90);
    ellipse(0, 0, f.size * 1.6, f.size);
    triangle(-f.size * 0.65, 0, -f.size * 1.35, -f.size * 0.55, -f.size * 1.35, f.size * 0.55);
    fill(220, 10, 12);
    circle(f.size * 0.38, -f.size * 0.12, 2.5);
    pop();
  }
}

function updateBubbles() {
  for (let i = bubbles.length - 1; i >= 0; i--) {
    const b = bubbles[i];
    b.x += b.drift || 0;
    b.y -= b.speed;
    if (b.vy) b.y += b.vy;
    if (b.life !== undefined) b.life--;
    noFill();
    stroke(180, 32, 100, b.alpha);
    strokeWeight(1.5);
    circle(b.x, b.y, b.r * 2);
    if (b.y < -20 || b.life === 0) {
      if (b.ring) bubbles.splice(i, 1);
      else bubbles[i] = makeBubble(random(width), height + random(10, 100));
    }
  }
  while (bubbles.length > 180) bubbles.shift();
  if (frameCountSafe % 4 === 0) bubbles.push(makeBubble(random(width), height + 8));
}

function drawDolphin(x, y) {
  push();
  translate(x, y + sin(frameCountSafe * 0.06) * 8);
  const leanAngle = pose.detected ? pose.lean * 0.25 : 0;
  rotate(leanAngle);
  scale(-1, 1);
  noStroke();
  // Tail
  fill(190, 32, 90);
  triangle(-58, 0, -91, -20, -83, 8);
  triangle(-58, 0, -91, 20, -83, -8);
  // Body
  fill(194, 30, 91);
  ellipse(0, 0, 112, 49);
  // Snout
  triangle(38, -5, 79, 4, 38, 12);
  // Belly
  fill(180, 12, 97);
  ellipse(12, 14, 62, 16);
  // Fin
  fill(194, 40, 74);
  triangle(-5, -12, 19, -34, 22, -7);
  triangle(4, 13, 26, 27, 18, 8);
  fill(225, 20, 10);
  circle(33, -7, 5);
  pop();
}

function drawHUD() {
  push();
  noStroke();
  fill(190, 20, 100, 90);
  textAlign(LEFT, TOP);
  textSize(18);
  text("BODY SWIM", 24, 22);
  textSize(13);
  fill(190, 15, 100, 65);
  text(pose.detected ? (pose.crouch ? "DEEP SEA · 深海" : pose.arms_spread ? "BUBBLE RING · 泡の輪" : "SWIM · 泳ぐ") : "STAND IN VIEW · カメラに全身を映してね", 24, 48);
  if (deepMix > 0.08) {
    fill(270, 55, 100, 85 * deepMix);
    textAlign(CENTER, CENTER);
    textSize(30);
    text("深海へ…", width / 2, height * 0.25);
    // Anglerfish lure
    fill(50, 75, 100, 90 * deepMix);
    circle(width * 0.72, height * 0.56, 15 + 5 * sin(frameCountSafe * 0.12));
    stroke(50, 55, 95, 80 * deepMix);
    strokeWeight(3);
    noFill();
    bezier(width * 0.66, height * 0.63, width * 0.65, height * 0.47, width * 0.72, height * 0.42, width * 0.72, height * 0.56);
  }
  pop();
}

function windowResized() {
  const holder = document.getElementById("canvas-holder");
  const w = Math.min(holder.clientWidth || 1100, 1100);
  resizeCanvas(w, w * 620 / 1100);
}
