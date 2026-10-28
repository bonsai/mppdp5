/**
 * DebugTest.pde
 * OSCなしで動作確認用 - 画面に何か描画されるか確認
 */

void setup() {
  size(1280, 720);
  frameRate(60);
  background(200, 220, 240);  // 明確な水色背景
}

void draw() {
  // 常に再描画
  background(200, 220, 240);
  
  // 中心に円
  fill(255, 100, 100);
  noStroke();
  ellipse(width/2, height/2, 100, 100);
  
  // テキスト
  fill(0);
  textSize(32);
  textAlign(CENTER, CENTER);
  text("DebugTest - これが見えたら描画OK", width/2, height/2 - 100);
  text("frameCount: " + frameCount, width/2, height/2 + 50);
  text("frameRate: " + nf(frameRate, 0, 1), width/2, height/2 + 100);
  
  // マウス位置に追従する小さな円
  fill(100, 255, 100);
  ellipse(mouseX, mouseY, 20, 20);
}

void keyPressed() {
  if (key == ' ') {
    background(255, 255, 100);
  }
}