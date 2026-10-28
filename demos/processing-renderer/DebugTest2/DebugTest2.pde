/**
 * DebugTest2.pde - レンダラー明示版
 * P2D / P3D を試す
 */

// ここを変更して試す: P2D, P3D, JAVA2D (デフォルト)
String RENDERER = P2D;

void settings() {
  // settings() で size() を呼ぶとレンダラーを確実に指定できる
  size(1280, 720, RENDERER);
}

void setup() {
  frameRate(60);
  // 背景を確実に塗る
  background(30, 144, 255);  // DodgerBlue - 真っ白ではない色
  
  // コンソールに出力
  println("=== DebugTest2 started ===");
  println("Renderer: " + RENDERER);
  println("Width: " + width + ", Height: " + height);
  println("Display: " + displayWidth + "x" + displayHeight);
}

void draw() {
  // 毎フレーム背景を塗り直す
  background(30, 144, 255);
  
  // 大きな円（中心）
  noStroke();
  fill(255, 255, 0);  // 黄色
  ellipse(width/2, height/2, 200, 200);
  
  // 小さな円（マウス追従）
  fill(255, 0, 0);  // 赤
  ellipse(mouseX, mouseY, 30, 30);
  
  // テキスト
  fill(255);
  textSize(28);
  textAlign(CENTER, CENTER);
  text("DebugTest2 - " + RENDERER, width/2, 50);
  text("frameCount: " + frameCount, width/2, 100);
  text("frameRate: " + nf(frameRate, 0, 1), width/2, 140);
  text("mouse: " + mouseX + ", " + mouseY, width/2, 180);
  
  // 四隅にマーカー
  stroke(255, 0, 255);
  strokeWeight(4);
  point(10, 10);
  point(width-10, 10);
  point(10, height-10);
  point(width-10, height-10);
  
  // コンソールにも出力（1秒に1回）
  if (frameCount % 60 == 0) {
    println("Frame " + frameCount + " - rate: " + nf(frameRate, 0, 1));
  }
}

void keyPressed() {
  if (key == '1') { RENDERER = JAVA2D; println("Restart sketch to apply: " + RENDERER); }
  if (key == '2') { RENDERER = P2D; println("Restart sketch to apply: " + RENDERER); }
  if (key == '3') { RENDERER = P3D; println("Restart sketch to apply: " + RENDERER); }
}