/**
 * CheckOSC5.pde - oscP5 ライブラリ読み込みテスト
 * コンソールにエラーが出るか確認
 */

void setup() {
  size(400, 300, JAVA2D);
  println("Testing oscP5 import...");
  
  try {
    // インポートテスト
    Class.forName("oscP5.OscP5");
    println("SUCCESS: oscP5.OscP5 class found");
    
    Class.forName("netP5.NetAddress");
    println("SUCCESS: netP5.NetAddress class found");
    
    // インスタンス化テスト
    oscP5.OscP5 oscP5 = new oscP5.OscP5(this, 9000);
    println("SUCCESS: OscP5 instance created on port 9000");
    
    fill(100, 255, 100);
    text("oscP5: OK", 20, 50);
    
  } catch (Exception e) {
    println("ERROR: " + e.getMessage());
    e.printStackTrace();
    
    fill(255, 100, 100);
    text("oscP5: FAILED", 20, 50);
    text(e.getMessage(), 20, 80);
  }
}

void draw() {
  background(30, 30, 50);
  fill(255);
  textSize(16);
  textAlign(CENTER, CENTER);
  text("Check console for results", width/2, height/2);
}