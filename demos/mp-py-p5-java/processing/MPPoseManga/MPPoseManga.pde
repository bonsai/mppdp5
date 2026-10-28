/*
 * MPPoseManga.pde
 * MediaPipe Pose (mp_osc_sender.py) -> OSC -> 手描き風漫画骨格描画
 */

import oscP5.*;
import netP5.*;
import java.sql.*; 

OscP5 oscP5;
NetAddress myRemoteLocation;

// Pose data
int numLandmarks = 33;
PVector[] lm = new PVector[numLandmarks];
float[] vis = new float[numLandmarks];
boolean hasPose = false;

// Settings
boolean showSkeleton = true;
boolean doBoil = true;
float wobbleAmp = 3.4;
int boilInterval = 3;
int frameIdx = 0;

// Paper background
PGraphics paper;

// Jitter
float[][] jitterX = new float[numLandmarks][4];
float[][] jitterY = new float[numLandmarks][4];

// DB
Connection dbConn = null;
String dbPath = "data/mppose_manga.db";
boolean dbEnabled = true;
int sessionId = -1;
String sessionStartTime = "";

void setup() {
  size(1280, 720);
  frameRate(60);
  smooth(8);
  
  oscP5 = new OscP5(this, 9000);
  
  initDB();
  
  for (int i = 0; i < numLandmarks; i++) {
    lm[i] = new PVector(0.5, 0.5);
    vis[i] = 0.0;
    for (int p = 0; p < 4; p++) {
      jitterX[i][p] = randomGaussian() * wobbleAmp;
      jitterY[i][p] = randomGaussian() * wobbleAmp;
    }
  }
  
  makePaper();
}

void initDB() {
  if (!dbEnabled) return;
  try {
    File dataDir = new File(sketchPath("data"));
    if (!dataDir.exists()) {
      dataDir.mkdirs();
    }
    Class.forName("org.sqlite.JDBC");
    dbConn = DriverManager.getConnection("jdbc:sqlite:" + sketchPath(dbPath));
    Statement stmt = dbConn.createStatement();
    stmt.executeUpdate("PRAGMA journal_mode=WAL;");
    stmt.executeUpdate("PRAGMA synchronous=NORMAL;");
    
    stmt.executeUpdate("CREATE TABLE IF NOT EXISTS sessions (" +
      "id INTEGER PRIMARY KEY AUTOINCREMENT," +
      "start_time TEXT DEFAULT (datetime('now','localtime'))," +
      "end_time TEXT," +
      "frame_count INTEGER DEFAULT 0," +
      "width INTEGER," +
      "height INTEGER," +
      "fps REAL" +
      ")");
    
    stmt.executeUpdate("CREATE TABLE IF NOT EXISTS screenshots (" +
      "id INTEGER PRIMARY KEY AUTOINCREMENT," +
      "session_id INTEGER," +
      "frame_idx INTEGER," +
      "filename TEXT NOT NULL," +
      "filepath TEXT NOT NULL," +
      "timestamp TEXT DEFAULT (datetime('now','localtime'))," +
      "has_pose INTEGER DEFAULT 0," +
      "FOREIGN KEY(session_id) REFERENCES sessions(id)" +
      ")");
    
    stmt.executeUpdate("CREATE TABLE IF NOT EXISTS frames (" +
      "id INTEGER PRIMARY KEY AUTOINCREMENT," +
      "session_id INTEGER," +
      "frame_idx INTEGER," +
      "has_pose INTEGER DEFAULT 0," +
      "timestamp TEXT DEFAULT (datetime('now','localtime'))," +
      "FOREIGN KEY(session_id) REFERENCES sessions(id)" +
      ")");
    
    stmt.close();
    
    PreparedStatement pstmt = dbConn.prepareStatement(
      "INSERT INTO sessions(start_time, width, height, fps) VALUES(datetime('now','localtime'), ?, ?, ?)",
      Statement.RETURN_GENERATED_KEYS
    );
    pstmt.setInt(1, width);
    pstmt.setInt(2, height);
    pstmt.setFloat(3, frameRate);
    pstmt.executeUpdate();
    ResultSet rs = pstmt.getGeneratedKeys();
    if (rs.next()) {
      sessionId = rs.getInt(1);
    }
    rs.close();
    pstmt.close();
    sessionStartTime = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new java.util.Date());
    println("[DB] Session started: id=" + sessionId);
  } catch (Exception e) {
    println("[DB ERROR] " + e.getMessage());
    dbEnabled = false;
  }
}

void makePaper() {
  paper = createGraphics(width, height);
  paper.beginDraw();
  paper.background(250, 248, 242);
  paper.loadPixels();
  for (int i = 0; i < paper.pixels.length; i++) {
    float n = random(-6, 6);
    color c = paper.pixels[i];
    float r = red(c) + n;
    float g = green(c) + n;
    float b = blue(c) + n*0.6;
    paper.pixels[i] = color(constrain(r,0,255), constrain(g,0,255), constrain(b,0,255));
  }
  paper.updatePixels();
  paper.stroke(235, 232, 224);
  paper.strokeWeight(1);
  for (int y = 0; y < height; y += 24) {
    paper.line(0, y, width, y);
  }
  paper.endDraw();
}

void draw() {
  frameIdx++;
  
  if (doBoil && frameIdx % boilInterval == 0) {
    for (int i = 0; i < numLandmarks; i++) {
      for (int p = 0; p < 4; p++) {
        jitterX[i][p] = lerp(jitterX[i][p], randomGaussian() * wobbleAmp * 2.0, 0.85);
        jitterY[i][p] = lerp(jitterY[i][p], randomGaussian() * wobbleAmp * 2.0, 0.85);
      }
    }
  }
  
  image(paper, 0, 0);
  
  if (dbEnabled && dbConn != null && sessionId > 0 && frameIdx % 30 == 0) {
    try {
      PreparedStatement pstmt = dbConn.prepareStatement(
        "INSERT INTO frames(session_id, frame_idx, has_pose) VALUES(?, ?, ?)"
      );
      pstmt.setInt(1, sessionId);
      pstmt.setInt(2, frameIdx);
      pstmt.setInt(3, hasPose ? 1 : 0);
      pstmt.executeUpdate();
      pstmt.close();
    } catch (Exception e) {
    }
  }
  
  drawMangaPose();
  
  drawHud();
}

void drawMangaPose() {
  int[][] connections = {
    {0,1},{1,2},{2,3},{3,7},
    {0,4},{4,5},{5,6},{6,8},
    {9,10},
    {11,12},{11,13},{13,15},{15,17},{15,19},{15,21},{17,19},
    {12,14},{14,16},{16,18},{16,20},{16,22},{18,20},
    {11,23},{12,24},{23,24},
    {23,25},{25,27},{27,29},{27,31},{29,31},
    {24,26},{26,28},{28,30},{28,32},{30,32}
  };
  
  strokeCap(ROUND);
  strokeJoin(ROUND);
  
  for (int c = 0; c < connections.length; c++) {
    int a = connections[c][0];
    int b = connections[c][1];
    if (a < 0 || a >= numLandmarks || b < 0 || b >= numLandmarks) continue;
    PVector pa = toScreen(a);
    PVector pb = toScreen(b);
    for (int pass = 0; pass < 4; pass++) {
      float jx1 = jitterX[a][pass % 4] * 1.8;
      float jy1 = jitterY[a][pass % 4] * 1.8;
      float jx2 = jitterX[b][pass % 4] * 1.8;
      float jy2 = jitterY[b][pass % 4] * 1.8;
      float wgt = map(pass, 0, 3, 6.0, 2.8);
      stroke(8);
      strokeWeight(wgt);
      line(pa.x + jx1, pa.y + jy1, pb.x + jx2, pb.y + jy2);
    }
  }
  
  noStroke();
  for (int i = 0; i < numLandmarks; i++) {
    PVector p = toScreen(i);
    float jx = ((jitterX[i][0] + jitterX[i][1] + jitterX[i][2]) / 3.0) * 2.0;
    float jy = ((jitterY[i][0] + jitterY[i][1] + jitterY[i][2]) / 3.0) * 2.0;
    fill(6);
    ellipse(p.x + jx, p.y + jy, 9, 9);
  }
}

PVector toScreen(int i) {
  float x = lm[i].x * width;
  float y = lm[i].y * height;
  return new PVector(x, y);
}

void drawHud() {
  fill(200, 0, 0);
  textSize(14);
  textAlign(LEFT, BOTTOM);
  text("hasPose: " + hasPose + " | OSC:127.0.0.1:9000", 12, height - 12);
  fill(40);
  textSize(14);
  textAlign(LEFT, TOP);
  String hud = "mp-py -> p5-java | ";
  hud += "boil:" + (doBoil?"ON":"OFF") + " ";
  hud += "wobble:" + nf(wobbleAmp, 0, 1) + " ";
  hud += "fps:" + nf(frameRate, 0, 0);
  text(hud, 12, 10);
  text("keys: b toggle | r reseed | s save", 12, 30);
}

void oscEvent(OscMessage msg) {
  String addr = msg.addrPattern();
  println("[OSC IN] " + addr + " | args: " + msg.arguments().length);
  
  if (addr.equals("/mppose/start")) {
    println("[OSC] start received");
    return;
  }
  
  if (addr.equals("/mppose/frame")) {
    if (msg.arguments().length >= 1) frameIdx = msg.get(0).intValue();
    return;
  }
  
  if (addr.equals("/mppose/landmark")) {
    if (msg.arguments().length >= 5) {
      int idx = msg.get(0).intValue();
      if (idx >= 0 && idx < numLandmarks) {
        float x = msg.get(1).floatValue();
        float y = msg.get(2).floatValue();
        float z = msg.get(3).floatValue();
        float v = msg.get(4).floatValue();
        lm[idx].set(x, y, z);
        vis[idx] = v;
        if (!hasPose) {
          println("[OSC] first landmark received -> hasPose = true");
        }
        hasPose = true;
      }
    }
    return;
  }
  
  if (addr.equals("/mppose/end")) {
    println("[OSC] end received");
    return;
  }
}

void keyPressed() {
  if (key == 'b' || key == 'B') {
    doBoil = !doBoil;
  } else if (key == 'r' || key == 'R') {
    for (int i = 0; i < numLandmarks; i++) {
      for (int p = 0; p < 4; p++) {
        jitterX[i][p] = randomGaussian() * wobbleAmp;
        jitterY[i][p] = randomGaussian() * wobbleAmp;
      }
    }
  } else if (key == 's' || key == 'S') {
    String fname = "mppose_manga_" + year() + nf(month(),2) + nf(day(),2) + "_" + nf(hour(),2) + nf(minute(),2) + nf(second(),2) + ".png";
    saveFrame(fname);
    if (dbEnabled && dbConn != null && sessionId > 0) {
      try {
        File dataDir = new File(sketchPath("data/screenshots"));
        if (!dataDir.exists()) {
          dataDir.mkdirs();
        }
        String srcFile = sketchPath(fname);
        String destFile = sketchPath("data/screenshots/" + fname);
        File src = new File(srcFile);
        if (src.exists()) {
          File dest = new File(destFile);
          java.nio.file.Files.copy(src.toPath(), dest.toPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
        PreparedStatement pstmt = dbConn.prepareStatement(
          "INSERT INTO screenshots(session_id, frame_idx, filename, filepath, has_pose) VALUES(?, ?, ?, ?, ?)"
        );
        pstmt.setInt(1, sessionId);
        pstmt.setInt(2, frameIdx);
        pstmt.setString(3, fname);
        pstmt.setString(4, "data/screenshots/" + fname);
        pstmt.setInt(5, hasPose ? 1 : 0);
        pstmt.executeUpdate();
        pstmt.close();
        println("[DB] Screenshot saved: " + fname);
      } catch (Exception e) {
        println("[DB ERROR] " + e.getMessage());
      }
    }
  } else if (key == ESC) {
    key = 0;
  }
}

void exit() {
  if (dbEnabled && dbConn != null && sessionId > 0) {
    try {
      PreparedStatement pstmt = dbConn.prepareStatement(
        "UPDATE sessions SET end_time = datetime('now','localtime'), frame_count = ? WHERE id = ?"
      );
      pstmt.setInt(1, frameIdx);
      pstmt.setInt(2, sessionId);
      pstmt.executeUpdate();
      pstmt.close();
      dbConn.close();
      println("[DB] Session closed: id=" + sessionId + " frames=" + frameIdx);
    } catch (Exception e) {
      println("[DB ERROR] " + e.getMessage());
    }
  }
  super.exit();
}
