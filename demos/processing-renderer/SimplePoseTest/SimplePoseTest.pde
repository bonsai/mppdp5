/**
 * SimplePoseTest.pde
 * 最小構成：OSCでランドマーク受信して描画するだけ
 * mp_osc_sender.py (port 9000) から /mppose/landmark を受信
 * レンダラー: JAVA2D (互換性重視)
 */

import oscP5.*;
import netP5.*;

OscP5 oscP5;

// 33 landmarks
int numLandmarks = 33;
PVector[] lm = new PVector[numLandmarks];
float[] vis = new float[numLandmarks];
boolean hasPose = false;

void setup() {
    size(1280, 720, JAVA2D);
  frameRate(60);
  smooth(4);
  
  // OSC 受信ポート 9000
  oscP5 = new OscP5(this, 9000);
  println("Listening OSC on port 9000...");
  
  for (int i = 0; i < numLandmarks; i++) {
    lm[i] = new PVector(0.5, 0.5);
    vis[i] = 0.0;
  }
  
  // 背景色（薄いグレーで白紙ではないことを確認）
  background(240, 240, 245);
}

void draw() {
  background(240, 240, 245);
  
  // デバッグ：常に何か描画
  fill(100, 180, 255);
  textSize(18);
  textAlign(LEFT, TOP);
  text("SimplePoseTest - OSC 9000", 20, 20);
  text("hasPose: " + hasPose, 20, 45);
  text("frameRate: " + nf(frameRate, 0, 1), 20, 70);
  
  if (hasPose) {
    drawSkeleton();
    drawLandmarks();
  } else {
    fill(180);
    textSize(24);
    textAlign(CENTER, CENTER);
    text("Waiting for OSC data...\nRun: py -3.11 mp_osc_sender.py --input 0 --port 9000", width/2, height/2);
  }
}

void drawSkeleton() {
  int[][] connections = {
    {0,1},{1,2},{2,3},{3,7},    // left face
    {0,4},{4,5},{5,6},{6,8},    // right face
    {9,10},                      // mouth
    {11,12},{11,13},{13,15},{15,17},{15,19},{15,21},  // left arm
    {12,14},{14,16},{16,18},{16,20},{16,22},          // right arm
    {11,23},{12,24},{23,24},     // torso
    {23,25},{25,27},{27,29},{27,31},  // left leg
    {24,26},{26,28},{28,30},{28,32}   // right leg
  };
  
  stroke(60, 60, 100);
  strokeWeight(3);
  strokeCap(ROUND);
  strokeJoin(ROUND);
  
  for (int[] c : connections) {
    int a = c[0], b = c[1];
    if (a < 0 || a >= numLandmarks || b < 0 || b >= numLandmarks) continue;
    if (vis[a] < 0.3 || vis[b] < 0.3) continue;
    
    PVector pa = toScreen(a);
    PVector pb = toScreen(b);
    line(pa.x, pa.y, pb.x, pb.y);
  }
}

void drawLandmarks() {
  noStroke();
  for (int i = 0; i < numLandmarks; i++) {
    if (vis[i] < 0.3) continue;
    PVector p = toScreen(i);
    // 手首は大きく
    if (i == 15 || i == 16) {
      fill(255, 100, 100);
      ellipse(p.x, p.y, 16, 16);
    } else {
      fill(80, 80, 120);
      ellipse(p.x, p.y, 10, 10);
    }
  }
}

PVector toScreen(int i) {
  return new PVector(lm[i].x * width, lm[i].y * height);
}

void oscEvent(OscMessage msg) {
  String addr = msg.addrPattern();
  
  if (addr.equals("/mppose/landmark")) {
    println("[DEBUG] landmark args: " + msg.arguments().length);
    if (msg.arguments().length >= 5) {
      int idx = msg.get(0).intValue();
      if (idx >= 0 && idx < numLandmarks) {
        float x = msg.get(1).floatValue();
        float y = msg.get(2).floatValue();
        float z = msg.get(3).floatValue();
        float v = msg.get(4).floatValue();
        lm[idx].set(x, y, z);
        vis[idx] = v;
        hasPose = true;
      }
    }
  }
  // 他のアドレスは無視（コンソールに出ないように）
}

void keyPressed() {
  if (key == 'r' || key == 'R') {
    // リセット
    for (int i = 0; i < numLandmarks; i++) {
      lm[i].set(0.5, 0.5);
      vis[i] = 0;
    }
    hasPose = false;
  }
  if (key == 's' || key == 'S') {
    saveFrame("pose_####.png");
    println("Saved screenshot");
  }
}
