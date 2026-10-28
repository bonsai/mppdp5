/**
 * NoLibTest.pde - ライブラリなしで動作確認
 * 何もインストール不要、Processing標準機能のみ
 */

void settings() {
  size(800, 600, JAVA2D);
}

void setup() {
  frameRate(60);
  background(30, 60, 90);
}

void draw() {
  background(30, 60, 90);
  
  // アニメーションする円
  float cx = width/2 + sin(frameCount * 0.05) * 100;
  float cy = height/2 + cos(frameCount * 0.03) * 80;
  
  noStroke();
  fill(255, 200, 50);
  ellipse(cx, cy, 60, 60);
  
  // マウス追従
  fill(50, 255, 100);
  ellipse(mouseX, mouseY, 20, 20);
  
  // テキスト
  fill(255);
  textSize(20);
  textAlign(CENTER, CENTER);
  text("NoLibTest - ライブラリ不要", width/2, 50);
  text("JAVA2D レンダラー動作中", width/2, 80);
  text("frameRate: " + nf(frameRate, 0, 1), width/2, height - 30);
  text("mouse: " + mouseX + ", " + mouseY, width/2, height - 10);
}