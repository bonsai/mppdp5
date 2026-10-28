// PoseRendererP5 — 描画専用 Processing スケッチ
// 検出 = MediaPipe 側 (Python) が契約 JSONL を出す / 描画 = このスケッチ
// 入力: data/poses-0001.jsonl (video2poses 契約: 1行 = 1フレーム x 1人)
// 操作: スペース=再生/停止, s=フレーム保存, b=震えON/OFF

final int[][] CONNECTIONS = {
  {0,1},{1,2},{2,3},{3,7},{0,4},{4,5},{5,6},{6,10},{9,10},
  {11,12},{11,13},{13,15},{15,17},{15,19},{15,21},{17,19},
  {12,14},{14,16},{16,18},{16,20},{16,22},{18,20},
  {11,23},{12,24},{23,24},{23,25},{24,26},{25,27},{26,28},
  {27,29},{28,30},{29,31},{30,32},{27,31},{28,32}
};

class Person {
  float[] xs = new float[33];
  float[] ys = new float[33];
  boolean[] has = new boolean[33];
}

ArrayList<ArrayList<Person>> frames = new ArrayList<ArrayList<Person>>();
PGraphics paper;
int playFrame = 0;
boolean playing = true;
boolean boil = true;
float wobble = 2.2;

void setup() {
  size(960, 540);
  loadPoses("poses-0001.jsonl");
  makePaper();
  frameRate(30);
  println("frames: " + frames.size());
}

void loadPoses(String name) {
  String[] lines = loadStrings(name);
  HashMap<Integer, ArrayList<Person>> byFrame = new HashMap<Integer, ArrayList<Person>>();
  int maxFrame = -1;
  for (String line : lines) {
    if (line == null || line.trim().length() == 0) continue;
    JSONObject o = parseJSONObject(line);
    int f = o.getInt("t_frame");
    JSONArray nodes = o.getJSONArray("nodes");
    Person p = new Person();
    for (int i = 0; i < nodes.size(); i++) {
      JSONObject n = nodes.getJSONObject(i);
      int id = n.getInt("id");
      if (id < 0 || id >= 33) continue;
      p.xs[id] = n.getFloat("x");
      p.ys[id] = n.getFloat("y");
      p.has[id] = true;
    }
    ArrayList<Person> list = byFrame.get(f);
    if (list == null) { list = new ArrayList<Person>(); byFrame.put(f, list); }
    list.add(p);
    if (f > maxFrame) maxFrame = f;
  }
  for (int f = 0; f <= maxFrame; f++) {
    ArrayList<Person> list = byFrame.get(f);
    frames.add(list == null ? new ArrayList<Person>() : list);
  }
}

void makePaper() {
  paper = createGraphics(width, height);
  paper.beginDraw();
  paper.background(250, 248, 242);
  paper.noStroke();
  for (int i = 0; i < width * height / 90; i++) {
    int v = 236 + (int) random(16);
    paper.fill(v, v, v - 4);
    paper.rect(random(width), random(height), 1.4, 1.4);
  }
  paper.endDraw();
}

void draw() {
  image(paper, 0, 0);
  if (frames.size() == 0) return;
  int f = playFrame % frames.size();
  float tt = boil ? (frameCount / 3) * 0.4 : 0;  // 震えは3フレームごとに更新
  for (Person p : frames.get(f)) {
    drawPerson(p, tt, f);
  }
  if (playing && frameCount % 2 == 0) playFrame++;  // 元は1fps素材なのでゆっくり再生
  fill(120);
  textSize(13);
  text("frame " + f + " / " + (frames.size() - 1) + "   [space] play/pause  [s] save  [b] boil", 12, height - 12);
}

void drawPerson(Person p, float tt, int f) {
  for (int ci = 0; ci < CONNECTIONS.length; ci++) {
    int a = CONNECTIONS[ci][0], b = CONNECTIONS[ci][1];
    if (!p.has[a] || !p.has[b]) continue;
    float x1 = p.xs[a] * width, y1 = p.ys[a] * height;
    float x2 = p.xs[b] * width, y2 = p.ys[b] * height;
    for (int pass = 0; pass < 3; pass++) {
      int shade = 40 + pass * 55;
      stroke(shade);
      strokeWeight(pass == 0 ? 2.4 : 1.4);
      drawJitteredLine(x1, y1, x2, y2, ci * 7.3 + pass * 3.1 + f * 0.05, tt);
    }
  }
  noStroke();
  fill(40);
  for (int i = 0; i < 33; i++) {
    if (p.has[i]) circle(p.xs[i] * width, p.ys[i] * height, 5);
  }
}

void drawJitteredLine(float x1, float y1, float x2, float y2, float seed, float tt) {
  float len = dist(x1, y1, x2, y2);
  int steps = max(4, (int) (len / 14));
  noFill();
  beginShape();
  for (int i = 0; i <= steps; i++) {
    float t = (float) i / steps;
    float env = sin(PI * t);  // 端点では震えゼロ (関節が離れない)
    float ox = (noise(seed + i * 0.28, tt) - 0.5) * 2 * wobble * env;
    float oy = (noise(seed + 100 + i * 0.28, tt + 50) - 0.5) * 2 * wobble * env;
    vertex(lerp(x1, x2, t) + ox, lerp(y1, y2, t) + oy);
  }
  endShape();
}

void keyPressed() {
  if (key == ' ') playing = !playing;
  if (key == 's' || key == 'S') saveFrame("frame-######.png");
  if (key == 'b' || key == 'B') boil = !boil;
}
