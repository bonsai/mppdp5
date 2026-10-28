import java.awt.*;
import java.awt.geom.Path2D;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.List;
import java.util.regex.*;

/**
 * PoseRenderer — 描画専用の実行ファイル（JAR）
 *
 * 役割分担:
 *   検出 = MediaPipe 側 (Python) が landmarks を契約フォーマットで出す
 *   描画 = この JAR が受け取って、手書き調モノクロ線画 PNG を出す
 * 受け渡しはファイル（JSONL）だけ。互いに import / 依存しない。
 *
 * 入力契約 (video2poses の poses-*.jsonl と同一):
 *   1行 = 1フレーム × 1人
 *   {"t_frame":0,"t_sec":0,"nodes":[{"id":0,"x":0.67,"y":0.36,"z":-0.39,"visibility":0.99}, ...]}
 *   x, y は 0..1 の正規化座標。同じ t_frame の行は同一フレームに重ねて描く。
 *
 * 使い方:
 *   java -jar pose-renderer.jar --in poses.jsonl --out frames/
 *   オプション: --w 1280 --h 720 --wobble 2.0 --passes 3 --seed 42
 */
public class PoseRenderer {

    // MediaPipe Pose の接続（骨）
    static final int[][] CONNECTIONS = {
        {0,1},{1,2},{2,3},{3,7},{0,4},{4,5},{5,6},{6,10},{9,10},
        {11,12},{11,13},{13,15},{15,17},{15,19},{15,21},{17,19},
        {12,14},{14,16},{16,18},{16,20},{16,22},{18,20},
        {11,23},{12,24},{23,24},{23,25},{24,26},{25,27},{26,28},
        {27,29},{28,30},{29,31},{30,32},{27,31},{28,32}
    };

    static final Pattern NUM = Pattern.compile("-?\\d+\\.\\d+(?:[eE][-+]?\\d+)?|-?\\d+");

    static class Person {
        double[][] xy = new double[33][2];
        boolean[] present = new boolean[33];
    }

    /** 1行を雑に・速くパースする（id 順に x,y を拾う） */
    static Person parseLine(String line) {
        Person p = new Person();
        Matcher mid = Pattern.compile("\"id\":\\s*(\\d+)").matcher(line);
        Matcher mx = Pattern.compile("\"x\":\\s*(-?[\\d.eE+-]+)").matcher(line);
        Matcher my = Pattern.compile("\"y\":\\s*(-?[\\d.eE+-]+)").matcher(line);
        List<Integer> ids = new ArrayList<>();
        while (mid.find()) ids.add(Integer.parseInt(mid.group(1)));
        List<Double> xs = new ArrayList<>();
        while (mx.find()) xs.add(Double.parseDouble(mx.group(1)));
        List<Double> ys = new ArrayList<>();
        while (my.find()) ys.add(Double.parseDouble(my.group(1)));
        int n = Math.min(ids.size(), Math.min(xs.size(), ys.size()));
        for (int i = 0; i < n; i++) {
            int id = ids.get(i);
            if (id >= 0 && id < 33) {
                p.xy[id][0] = xs.get(i);
                p.xy[id][1] = ys.get(i);
                p.present[id] = true;
            }
        }
        return p;
    }

    static int frameOf(String line) {
        Matcher m = Pattern.compile("\"t_frame\":\\s*(\\d+)").matcher(line);
        return m.find() ? Integer.parseInt(m.group(1)) : -1;
    }

    /** 2点間を分割し、滑らかな震えを加えた点列を返す */
    static double[][] jitteredSegment(double x1, double y1, double x2, double y2,
                                      double wobble, Random rng) {
        double len = Math.hypot(x2 - x1, y2 - y1);
        int steps = Math.max(4, (int) (len / 14));
        double[][] pts = new double[steps + 1][2];
        double[] ox = new double[steps + 1];
        double[] oy = new double[steps + 1];
        for (int i = 0; i <= steps; i++) {
            ox[i] = rng.nextGaussian() * wobble;
            oy[i] = rng.nextGaussian() * wobble;
        }
        // 移動平均で滑らかに（手の震えは低周波）
        for (int k = 0; k < 2; k++) {
            double[] sx = new double[steps + 1], sy = new double[steps + 1];
            for (int i = 0; i <= steps; i++) {
                double ax = 0, ay = 0; int c = 0;
                for (int j = -2; j <= 2; j++) {
                    int idx = i + j;
                    if (idx >= 0 && idx <= steps) { ax += ox[idx]; ay += oy[idx]; c++; }
                }
                sx[i] = ax / c; sy[i] = ay / c;
            }
            ox = sx; oy = sy;
        }
        ox[0] = oy[0] = ox[steps] = oy[steps] = 0; // 端点は固定
        for (int i = 0; i <= steps; i++) {
            double t = (double) i / steps;
            pts[i][0] = x1 + (x2 - x1) * t + ox[i];
            pts[i][1] = y1 + (y2 - y1) * t + oy[i];
        }
        return pts;
    }

    static void drawPerson(Graphics2D g, Person p, int W, int H,
                           double wobble, int passes, long seed, int frameIdx) {
        for (int[] c : CONNECTIONS) {
            if (!p.present[c[0]] || !p.present[c[1]]) continue;
            double x1 = p.xy[c[0]][0] * W, y1 = p.xy[c[0]][1] * H;
            double x2 = p.xy[c[1]][0] * W, y2 = p.xy[c[1]][1] * H;
            for (int pass = 0; pass < passes; pass++) {
                Random rng = new Random(seed + frameIdx * 1000003L + c[0] * 1009L + c[1] * 9176L + pass * 131L);
                int shade = 40 + pass * 55;
                g.setColor(new Color(shade, shade, shade));
                g.setStroke(new BasicStroke(pass == 0 ? 2.4f : 1.4f,
                        BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
                double[][] pts = jitteredSegment(x1, y1, x2, y2, wobble, rng);
                Path2D path = new Path2D.Double();
                path.moveTo(pts[0][0], pts[0][1]);
                for (int i = 1; i < pts.length; i++) path.lineTo(pts[i][0], pts[i][1]);
                g.draw(path);
            }
        }
        // 関節の丸
        g.setColor(new Color(40, 40, 40));
        for (int i = 0; i < 33; i++) {
            if (!p.present[i]) continue;
            double x = p.xy[i][0] * W, y = p.xy[i][1] * H;
            g.fillOval((int) (x - 3), (int) (y - 3), 6, 6);
        }
    }

    public static void main(String[] args) throws Exception {
        System.setProperty("java.awt.headless", "true");
        String in = null, outDir = "frames";
        int W = 1280, H = 720, passes = 3;
        double wobble = 2.0;
        long seed = 42;
        for (int i = 0; i < args.length - 1; i++) {
            switch (args[i]) {
                case "--in" -> in = args[++i];
                case "--out" -> outDir = args[++i];
                case "--w" -> W = Integer.parseInt(args[++i]);
                case "--h" -> H = Integer.parseInt(args[++i]);
                case "--wobble" -> wobble = Double.parseDouble(args[++i]);
                case "--passes" -> passes = Integer.parseInt(args[++i]);
                case "--seed" -> seed = Long.parseLong(args[++i]);
            }
        }
        if (in == null) {
            System.err.println("usage: java -jar pose-renderer.jar --in poses.jsonl --out frames/ [--w 1280 --h 720 --wobble 2.0 --passes 3]");
            System.exit(1);
        }
        Path outPath = Paths.get(outDir);
        Files.createDirectories(outPath);

        // フレームごとに人をまとめる
        Map<Integer, List<Person>> frames = new TreeMap<>();
        for (String line : Files.readAllLines(Paths.get(in))) {
            line = line.trim();
            if (line.isEmpty()) continue;
            int f = frameOf(line);
            if (f < 0) continue;
            frames.computeIfAbsent(f, k -> new ArrayList<>()).add(parseLine(line));
        }

        // 紙テクスチャ（一度だけ作って使い回す）
        BufferedImage paperTex = new BufferedImage(W, H, BufferedImage.TYPE_INT_RGB);
        {
            Graphics2D pg = paperTex.createGraphics();
            pg.setColor(new Color(250, 248, 242));
            pg.fillRect(0, 0, W, H);
            pg.dispose();
            Random nrng = new Random(7);
            for (int i = 0; i < W * H / 90; i++) {
                int v = 238 + nrng.nextInt(14);
                paperTex.setRGB(nrng.nextInt(W), nrng.nextInt(H), (v << 16) | (v << 8) | (v - 4));
            }
        }

        int count = 0;
        for (Map.Entry<Integer, List<Person>> e : frames.entrySet()) {
            BufferedImage img = new BufferedImage(W, H, BufferedImage.TYPE_INT_RGB);
            Graphics2D g = img.createGraphics();
            g.drawImage(paperTex, 0, 0, null);
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            for (Person p : e.getValue()) {
                drawPerson(g, p, W, H, wobble, passes, seed, e.getKey());
            }
            g.dispose();
            Path file = outPath.resolve(String.format("frame_%06d.png", e.getKey()));
            javax.imageio.ImageIO.write(img, "png", file.toFile());
            count++;
        }
        System.out.println("rendered " + count + " frames -> " + outDir);
    }
}
