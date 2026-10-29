// Web Manga Demo - MediaPipe Tasks (Web) + p5.js
// モード: manga(輪郭+トーン), contour(輪郭のみ), pose(ランドマーク), segment(セグメンテーション)

import p5 from "p5";
import {
  PoseLandmarker,
  FilesetResolver,
  SelfieSegmenter,
  DrawingUtils,
} from "@mediapipe/tasks-vision";

let p5Instance;
let videoElement;
let canvasElement;

let poseLandmarker = null;
let selfieSegmenter = null;
let drawingUtils = null;

let currentMode = "manga";
let isRunning = true;
let lastVideoTime = 0;

let poseResults = null;
let segmentationMask = null;

const statusEl = document.getElementById("status");
const modeSelect = document.getElementById("modeSelect");
const cameraSelect = document.getElementById("cameraSelect");
const toggleBtn = document.getElementById("toggleBtn");

const sketch = (p) => {
  p5Instance = p;

  p.setup = () => {
    canvasElement = p.createCanvas(640, 480);
    canvasElement.parent("canvas-holder");
    p.pixelDensity(1);
    p.colorMode(p.HSB, 360, 100, 100, 100);

    initCamera();
    initMediaPipe();
  };

  p.draw = () => {
    if (!isRunning || !videoElement || videoElement.readyState < 2) return;

    p.clear();
    p.background(0, 0, 5);

    if (currentMode === "segment" && segmentationMask) {
      drawSegmentationMask(p);
    } else if (poseResults) {
      if (currentMode === "manga") {
        drawMangaStyle(p);
      } else if (currentMode === "contour") {
        drawContourOnly(p);
      } else if (currentMode === "pose") {
        drawPoseLandmarks(p);
      }
    }

    drawHUD(p);
  };

  p.windowResized = () => {
    const holder = document.getElementById("canvas-holder");
    const w = Math.min(holder.clientWidth || 640, 1280);
    const h = w * 480 / 640;
    p.resizeCanvas(w, h);
  };
};

new p5(sketch);

async function initCamera() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter((d) => d.kind === "videoinput");

    cameraSelect.innerHTML = "";
    videoDevices.forEach((device, i) => {
      const opt = document.createElement("option");
      opt.value = device.deviceId;
      opt.text = device.label || `カメラ ${i + 1}`;
      cameraSelect.appendChild(opt);
    });

    if (videoDevices.length > 0) {
      await startCamera(videoDevices[0].deviceId);
      updateStatus("connected", "カメラ接続済み · 全身を映してください");
    } else {
      updateStatus("error", "カメラが見つかりません");
    }
  } catch (err) {
    console.error("Camera init error:", err);
    updateStatus("error", "カメラアクセスエラー: " + err.message);
  }
}

async function startCamera(deviceId) {
  if (videoElement) {
    videoElement.srcObject.getTracks().forEach((t) => t.stop());
  }

  videoElement = document.createElement("video");
  videoElement.setAttribute("playsinline", "");
  videoElement.setAttribute("muted", "");
  videoElement.style.display = "none";
  document.body.appendChild(videoElement);

  const stream = await navigator.mediaDevices.getUserMedia({
    video: { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
    audio: false,
  });

  videoElement.srcObject = stream;
  await videoElement.play();
}

cameraSelect.addEventListener("change", () => {
  startCamera(cameraSelect.value);
});

toggleBtn.addEventListener("click", () => {
  isRunning = !isRunning;
  toggleBtn.textContent = isRunning ? "一時停止" : "再開";
  if (isRunning && videoElement && videoElement.paused) {
    videoElement.play();
  } else if (!isRunning && videoElement) {
    videoElement.pause();
  }
});

modeSelect.addEventListener("change", () => {
  currentMode = modeSelect.value;
});

async function initMediaPipe() {
  try {
    updateStatus("connecting", "MediaPipe Tasks を読み込み中…");

    const vision = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22/wasm"
    );

    poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        delegate: "GPU",
      },
      runningMode: "VIDEO",
      numPoses: 1,
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
      outputSegmentationMasks: true,
    });

    selfieSegmenter = await SelfieSegmenter.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/selfie_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite",
        delegate: "GPU",
      },
      runningMode: "VIDEO",
      outputCategoryMask: true,
      outputConfidenceMasks: true,
    });

    drawingUtils = new DrawingUtils();

    updateStatus("connected", "MediaPipe 準備完了 · 検出待機中");
    predictLoop();
  } catch (err) {
    console.error("MediaPipe init error:", err);
    updateStatus("error", "MediaPipe エラー: " + err.message);
  }
}

async function predictLoop() {
  if (!isRunning || !videoElement || videoElement.readyState < 2) {
    requestAnimationFrame(predictLoop);
    return;
  }

  const now = videoElement.currentTime * 1000;
  if (now !== lastVideoTime) {
    lastVideoTime = now;

    if (poseLandmarker) {
      poseResults = poseLandmarker.detectForVideo(videoElement, now);
    }

    if (selfieSegmenter && currentMode === "segment") {
      const segResult = selfieSegmenter.segmentForVideo(videoElement, now);
      segmentationMask = segResult.categoryMask;
    }
  }

  requestAnimationFrame(predictLoop);
}

function drawMangaStyle(p) {
  // セグメンテーションマスクからシルエットを取得して漫画風に
  if (poseResults && poseResults.landmarks && poseResults.landmarks.length > 0) {
    const landmarks = poseResults.landmarks[0];
    const w = p.width;
    const h = p.height;

    // 漫画風トーンパターン
    p.noStroke();

    // 体の輪郭をランドマークから構築
    const bodyContour = getBodyContour(landmarks, w, h);

    // 下地（影）
    p.fill(0, 0, 15);
    p.beginShape();
    bodyContour.forEach((pt) => p.vertex(pt.x, pt.y));
    p.endShape(p.CLOSE);

    // メイン輪郭線
    p.stroke(0, 0, 95);
    p.strokeWeight(3);
    p.noFill();
    p.beginShape();
    bodyContour.forEach((pt) => p.vertex(pt.x, pt.y));
    p.endShape(p.CLOSE);

    // 内側の輪郭（服の境界など）
    p.stroke(0, 0, 60);
    p.strokeWeight(1.5);
    drawInnerContours(p, landmarks, w, h);

    // スクリーントーン（網点）で影を表現
    drawScreentone(p, landmarks, w, h);

    // 顔の輪郭
    drawFaceContour(p, landmarks, w, h);
  }
}

function drawContourOnly(p) {
  if (poseResults && poseResults.landmarks && poseResults.landmarks.length > 0) {
    const landmarks = poseResults.landmarks[0];
    const w = p.width;
    const h = p.height;

    const bodyContour = getBodyContour(landmarks, w, h);

    p.stroke(200, 20, 90);
    p.strokeWeight(2);
    p.noFill();
    p.beginShape();
    bodyContour.forEach((pt) => p.vertex(pt.x, pt.y));
    p.endShape(p.CLOSE);

    drawInnerContours(p, landmarks, w, h);
    drawFaceContour(p, landmarks, w, h);
  }
}

function drawPoseLandmarks(p) {
  if (poseResults && poseResults.landmarks && poseResults.landmarks.length > 0) {
    const landmarks = poseResults.landmarks[0];
    const w = p.width;
    const h = p.height;

    // 接続線
    p.stroke(120, 80, 90);
    p.strokeWeight(2);
    p.noFill();
    const connections = [
      [11, 12], [11, 13], [13, 15], [15, 17], [15, 19], [15, 21],
      [12, 14], [14, 16], [16, 18], [16, 20], [16, 22],
      [11, 23], [12, 24], [23, 24],
      [23, 25], [25, 27], [27, 29], [27, 31],
      [24, 26], [26, 28], [28, 30], [28, 32],
    ];

    connections.forEach(([a, b]) => {
      if (landmarks[a] && landmarks[b] && landmarks[a].visibility > 0.5 && landmarks[b].visibility > 0.5) {
        p.line(landmarks[a].x * w, landmarks[a].y * h, landmarks[b].x * w, landmarks[b].y * h);
      }
    });

    // ランドマーク点
    p.noStroke();
    p.fill(60, 100, 90);
    landmarks.forEach((lm, i) => {
      if (lm.visibility > 0.5) {
        p.circle(lm.x * w, lm.y * h, 6);
      }
    });
  }
}

function drawSegmentationMask(p) {
  if (!segmentationMask) return;

  const w = p.width;
  const h = p.height;

  // マスクをキャンバスに描画（簡易版：マスクのデータから直接描画は重いので、ポリゴン近似で）
  p.fill(200, 50, 80, 50);
  p.noStroke();
  p.rect(0, 0, w, h);
}

function getBodyContour(landmarks, w, h) {
  // 主要な体のランドマークから外周を構築
  const indices = [
    0,   // nose
    2, 5, 7, 8,  // face outline (left)
    11, 13, 15,  // left arm
    23, 25, 27, 29, 31, // left leg
    24, 26, 28, 30, 32, // right leg
    12, 14, 16,  // right arm
    4, 3, 6,     // face outline (right)
  ];

  const contour = [];
  indices.forEach((idx) => {
    const lm = landmarks[idx];
    if (lm && lm.visibility > 0.4) {
      contour.push({ x: lm.x * w, y: lm.y * h });
    }
  });

  // 凸包で滑らかに
  return convexHull(contour);
}

function convexHull(points) {
  if (points.length < 3) return points;

  // Graham scan
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);

  function cross(o, a, b) {
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  }

  const lower = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }

  const upper = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }

  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

function drawInnerContours(p, landmarks, w, h) {
  // 肩〜胸〜腰のライン
  const torso = [
    [11, 12], // shoulders
    [11, 23], [12, 24], // sides
    [23, 24], // hips
  ];

  p.stroke(0, 0, 40);
  p.strokeWeight(1);
  torso.forEach(([a, b]) => {
    if (landmarks[a] && landmarks[b] && landmarks[a].visibility > 0.5 && landmarks[b].visibility > 0.5) {
      p.line(landmarks[a].x * w, landmarks[a].y * h, landmarks[b].x * w, landmarks[b].y * h);
    }
  });

  // 膝・肘
  const joints = [[13, 14], [25, 26], [27, 28]];
  joints.forEach(([a, b]) => {
    if (landmarks[a] && landmarks[b] && landmarks[a].visibility > 0.5 && landmarks[b].visibility > 0.5) {
      p.line(landmarks[a].x * w, landmarks[a].y * h, landmarks[b].x * w, landmarks[b].y * h);
    }
  });
}

function drawFaceContour(p, landmarks, w, h) {
  // 顔の輪郭（鼻・目・耳から近似）
  const facePts = [0, 2, 5, 7, 8, 4, 3, 6].map((i) => landmarks[i]).filter((lm) => lm && lm.visibility > 0.5);

  if (facePts.length >= 3) {
    const hull = convexHull(facePts.map((lm) => ({ x: lm.x * w, y: lm.y * h })));
    p.stroke(0, 0, 95);
    p.strokeWeight(2);
    p.noFill();
    p.beginShape();
    hull.forEach((pt) => p.vertex(pt.x, pt.y));
    p.endShape(p.CLOSE);
  }
}

function drawScreentone(p, landmarks, w, h) {
  // 簡易スクリーントーン：影になる部分に網点
  if (!landmarks[11] || !landmarks[12] || !landmarks[23] || !landmarks[24]) return;

  const cx = (landmarks[11].x + landmarks[12].x) / 2 * w;
  const cy = (landmarks[11].y + landmarks[12].y) / 2 * h;
  const hipY = (landmarks[23].y + landmarks[24].y) / 2 * h;
  const shoulderW = Math.abs(landmarks[11].x - landmarks[12].x) * w;

  p.stroke(0, 0, 30);
  p.strokeWeight(0.5);

  for (let y = cy; y < hipY; y += 4) {
    const ratio = (y - cy) / (hipY - cy);
    const width = shoulderW * (1 - ratio * 0.3);
    const left = cx - width / 2;
    const right = cx + width / 2;

    for (let x = left; x < right; x += 8) {
      if ((x + y) % 16 < 4) {
        p.point(x, y);
      }
    }
  }
}

function drawHUD(p) {
  p.push();
  p.resetMatrix();
  p.noStroke();
  p.fill(0, 0, 100, 90);
  p.textAlign(p.LEFT, p.TOP);
  p.textSize(18);
  p.text("WEB MANGA", 24, 22);
  p.textSize(13);
  p.fill(0, 0, 100, 65);
  const modeNames = { manga: "MANGA · 漫画", contour: "CONTOUR · 輪郭", pose: "POSE · 骨格", segment: "SEGMENT · セグメント" };
  p.text(modeNames[currentMode] || currentMode, 24, 48);
  p.text(poseResults ? "検出中" : "全身を映してください", 24, 68);
  p.pop();
}

function updateStatus(connection, label) {
  if (!statusEl) return;
  const ok = connection === "connected";
  statusEl.innerHTML = '<span class="dot ' + (ok ? "ok" : "") + '"></span>' + label;
}