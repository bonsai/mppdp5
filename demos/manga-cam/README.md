# manga_cam デモ — リアルタイム漫画線画パイプライン

video2storyboard のデモとして採用（2026-10-28）。動画・カメラ映像をその場で
「漫画の線画」に変換するリアルタイム版。絵コンテ生成の前段（線画化）の実験場。

## パイプライン（manga-pipeline.puml 参照）

疎結合が原則。ステージ間は契約（frame / landmarks / mask / contours）だけでつなぎ、
実装同士は import しない。連携プロジェクト video2poses と同じ流儀。

1. 線画抽出: bilateral + Canny + 輪郭（コードのみ、モデル不使用）
2. 重要度付け: 勾配の強さ×輪郭の長さ → 重要な線は濃く、他はうっすら
3. 手書き調: 輪郭の点列を震わせて重ね描き（震えは boil フレームごとに更新）
4. 人物: MediaPipe Pose の骨格を別レイヤーで常に濃く
5. 建物: Mask2Former (ADE20K) の建物マスクで重要度ブースト（N フレームに1回だけ計算）
6. トーン: 階調を量子化して紙の下に敷く

描画は差し替え可能: landmarks + contours を OSC で送れば、
Processing スケッチ側で描画する分割構成も同じ契約で動く。

## 使い方

```
pip install opencv-python numpy mediapipe
# 建物ブーストを使う場合のみ: pip install transformers pillow torch

python manga_cam.py                  # Webカメラ
python manga_cam.py --input in.mp4 --save out.mp4
python manga_cam.py --buildings      # 建物ブーストON
```

キー: q=終了 / p=骨格 / b=建物 / t=トーン / s=フレーム保存

## 描画専用 JAR: pose-renderer

役割分担の実物。検出（MediaPipe / Python）とはファイルだけでつながる描画実行ファイル。

- 入力: video2poses 契約の poses-*.jsonl（1行 = 1フレーム×1人、nodes に正規化座標）
- 出力: 手書き調モノクロ骨格の PNG 連番（紙テクスチャ＋震え＋重ね描き）
- ビルド: `javac -d classes PoseRenderer.java && jar --create --file pose-renderer.jar --main-class PoseRenderer -C classes .`
- 実行: `java -jar pose-renderer.jar --in poses.jsonl --out frames/ [--w 1280 --h 720 --wobble 2.0 --passes 3]`
- 依存: Java 標準ライブラリのみ（外部ライブラリなし）

## Processing 版とローカル表示

- `processing/PoseRendererP5/PoseRendererP5.pde` — JAR と同じ契約を読む Processing スケッチ（再生つき）
- `view-local.ps1` — Windows 用: 両リポを clone/pull し、poses を data/ に置いて、そのまま実行/起動する

```
.\view-local.ps1
```
