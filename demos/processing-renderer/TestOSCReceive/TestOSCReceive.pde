/**
 * TestOSCReceive.pde - oscP5ライブラリの動作確認用
 * ライブラリが正しくインストールされているかテスト
 */

// oscP5がインストールされていればこの行でエラーにならない
import oscP5.*;
import netP5.*;

OscP5 oscP5;
boolean oscReady = false;

void settings() {
  size(800, 600, JAVA2D);
}

void setup() {
  frameRate(60);
  background(50, 50, 80);
  
  fill(255);
  textSize(20);
  textAlign(CENTER, CENTER);
  text("Testing oscP5 library...", width/2, height/2 - 50);
  
  try {
    oscP5 = new OscP5(this, 9000);
    oscReady = true;
    println("SUCCESS: oscP5 created on port 9000");
  } catch (Exception e) {
    println("ERROR: " + e.getMessage());
    e.printStackTrace();
  }
}

void draw() {
  background(50, 50, 80);
  
  fill(255);
  textSize(18);
  textAlign(CENTER, CENTER);
  
  if (oscReady) {
    fill(100, 255, 100);
    text("oscP5: READY on port 9000", width/2, height/2 - 30);
    text("Run mp_osc_sender.py to send data", width/2, height/2 + 10);
  } else {
    fill(255, 100, 100);
    text("oscP5: FAILED - Check console", width/2, height/2 - 30);
    text("Install oscP5 from Library Manager", width/2, height/2 + 10);
  }
  
  text("frameRate: " + nf(frameRate, 0, 1), width/2, height - 30);
}