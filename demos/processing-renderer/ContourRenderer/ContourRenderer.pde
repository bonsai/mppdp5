/**
 * Contour Renderer - Processing sketch to render contour JSONL from mppdp5 adapters.
 * 
 * Reads contour.jsonl (from ContourAdapter) and renders the lines in real-time.
 * 
 * Usage:
 *   1. Run contour adapter: python demo_contour.py --input video.mp4 --output work/contour.jsonl
 *   2. Open this sketch in Processing
 *   3. Press 'p' to load contour.jsonl and play
 *   4. Press 's' to save frames as PNG sequence
 */

import processing.serial.*;
import processing.video.*;

ArrayList<ContourFrame> frames;
int currentFrame = 0;
boolean playing = false;
boolean saveFrames = false;
String jsonlPath = "work/contour.jsonl";
int frameRate = 30;

class ContourFrame {
  int frameIndex;
  float timestamp;
  ArrayList<PVector> points;
  ArrayList<int[]> connections;
  int imageWidth;
  int imageHeight;
  
  ContourFrame(int idx, float ts, int w, int h) {
    frameIndex = idx;
    timestamp = ts;
    imageWidth = w;
    imageHeight = h;
    points = new ArrayList<PVector>();
    connections = new ArrayList<int[]>();
  }
  
  void addPoint(float x, float y) {
    points.add(new PVector(x, y));
  }
  
  void addConnection(int start, int end) {
    connections.add(new int[]{start, end});
  }
}

void setup() {
  size(1280, 720);
  frames = new ArrayList<ContourFrame>();
  textFont(createFont("Monospaced", 14));
  println("Contour Renderer ready.");
  println("Press 'l' to load JSONL file");
  println("Press 'p' to play/pause");
  println("Press 's' to save frames");
  println("Left/Right arrows to step frames");
}

void draw() {
  background(0);
  
  if (frames.size() == 0) {
    fill(255);
    textAlign(CENTER, CENTER);
    text("No frames loaded. Press 'l' to load " + jsonlPath, width/2, height/2);
    return;
  }
  
  // Draw current frame
  if (currentFrame >= 0 && currentFrame < frames.size()) {
    ContourFrame frame = frames.get(currentFrame);
    drawContourFrame(frame);
  }
  
  // Draw UI
  drawUI();
  
  // Auto-advance if playing
  if (playing && frameCount % (60/frameRate) == 0) {
    currentFrame++;
    if (currentFrame >= frames.size()) {
      currentFrame = 0; // Loop
    }
  }
  
  // Save frame if requested
  if (saveFrames) {
    saveFrame("output/frame_####.png");
  }
}

void drawContourFrame(ContourFrame frame) {
  pushMatrix();
  
  // Scale to fit window while maintaining aspect
  float scaleX = (float)width / frame.imageWidth;
  float scaleY = (float)height / frame.imageHeight;
  float scale = min(scaleX, scaleY) * 0.9;
  
  translate((width - frame.imageWidth * scale) / 2, (height - frame.imageHeight * scale) / 2);
  scale(scale);
  
  // Draw connections (lines)
  if (frame.connections != null && frame.connections.size() > 0) {
    stroke(255, 255, 255, 200);
    strokeWeight(2);
    noFill();
    
    for (int[] conn : frame.connections) {
      if (conn[0] < frame.points.size() && conn[1] < frame.points.size()) {
        PVector p1 = frame.points.get(conn[0]);
        PVector p2 = frame.points.get(conn[1]);
        line(p1.x, p1.y, p2.x, p2.y);
      }
    }
  }
  
  // Draw points
  if (frame.points != null) {
    stroke(255, 100, 100);
    strokeWeight(4);
    for (PVector p : frame.points) {
      point(p.x, p.y);
    }
  }
  
  popMatrix();
}

void drawUI() {
  fill(0, 180);
  noStroke();
  rect(0, 0, width, 100);
  
  fill(255);
  textAlign(LEFT, TOP);
  text("Contour Renderer | Frame: " + currentFrame + " / " + (frames.size()-1) + 
       " | " + (playing ? "PLAYING" : "PAUSED") + 
       " | " + (saveFrames ? "SAVING" : ""), 10, 10);
  
  if (currentFrame < frames.size()) {
    ContourFrame f = frames.get(currentFrame);
    text("Timestamp: " + nf(f.timestamp, 1, 3) + "s | Points: " + f.points.size() + 
         " | Connections: " + f.connections.size() + 
         " | Source: " + f.imageWidth + "x" + f.imageHeight, 10, 35);
  }
  
  text("Keys: [L]oad  [P]lay  [S]ave  [<-][->] step  [R]eset  [+/-] speed", 10, 60);
}

void keyPressed() {
  switch(key) {
    case 'l':
    case 'L':
      loadJSONL(jsonlPath);
      break;
    case 'p':
    case 'P':
      playing = !playing;
      break;
    case 's':
    case 'S':
      saveFrames = !saveFrames;
      if (saveFrames) {
        println("Saving frames to output/ ...");
      } else {
        println("Stopped saving.");
      }
      break;
    case 'r':
    case 'R':
      currentFrame = 0;
      break;
    case '+':
    case '=':
      frameRate = min(60, frameRate + 5);
      println("Frame rate: " + frameRate);
      break;
    case '-':
    case '_':
      frameRate = max(1, frameRate - 5);
      println("Frame rate: " + frameRate);
      break;
  }
}

void keyReleased() {
  if (keyCode == LEFT) {
    currentFrame = max(0, currentFrame - 1);
  } else if (keyCode == RIGHT) {
    currentFrame = min(frames.size() - 1, currentFrame + 1);
  }
}

void loadJSONL(String path) {
  println("Loading: " + path);
  frames.clear();
  
  String[] lines = loadStrings(path);
  if (lines == null || lines.length == 0) {
    println("Error: Could not load file or file empty");
    return;
  }
  
  int loaded = 0;
  int errors = 0;
  
  for (String line : lines) {
    line = line.trim();
    if (line.isEmpty()) continue;
    
    try {
      JSONObject json = parseJSONObject(line);
      ContourFrame frame = parseContourFrame(json);
      if (frame != null) {
        frames.add(frame);
        loaded++;
      }
    } catch (Exception e) {
      errors++;
      if (errors < 5) println("Parse error: " + e.getMessage());
    }
  }
  
  currentFrame = 0;
  println("Loaded " + loaded + " frames (" + errors + " errors)");
}

ContourFrame parseContourFrame(JSONObject json) {
  int frameIndex = json.getInt("frame_index");
  float timestamp = json.getFloat("timestamp");
  int width = json.getInt("image_width");
  int height = json.getInt("image_height");
  boolean success = json.getBoolean("success");
  
  if (!success) {
    // Still create frame but empty
    return new ContourFrame(frameIndex, timestamp, width, height);
  }
  
  ContourFrame frame = new ContourFrame(frameIndex, timestamp, width, height);
  
  // Parse points
  JSONArray pointsArray = json.getJSONArray("points");
  if (pointsArray != null) {
    for (int i = 0; i < pointsArray.size(); i++) {
      JSONArray pt = pointsArray.getJSONArray(i);
      if (pt.size() >= 2) {
        float x = pt.getFloat(0);
        float y = pt.getFloat(1);
        frame.addPoint(x, y);
      }
    }
  }
  
  // Parse connections
  JSONArray connArray = json.getJSONArray("connections");
  if (connArray != null) {
    for (int i = 0; i < connArray.size(); i++) {
      JSONArray conn = connArray.getJSONArray(i);
      if (conn.size() >= 2) {
        int start = conn.getInt(0);
        int end = conn.getInt(1);
        frame.addConnection(start, end);
      }
    }
  }
  
  return frame;
}