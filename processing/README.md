# Processing Java renderer

このフォルダは描画専用のProcessingスケッチです。カメラ取得・MediaPipe・動きの解釈は親ディレクトリの `server.py` が担当します。

## 起動

1. Processing 4をインストール
2. Processing IDEの **Sketch → Import Library… → Manage Libraries…** から `oscP5` をインストール
3. `psychedelic_pose_projection.pde` をProcessing IDEで開いてRun
4. リポジトリルートで `python server.py` を起動

PythonはOSCを `127.0.0.1:12000/UDP` に送信します。海中ゲームも必要なら同時に `http://127.0.0.1:8765` を開きます。

## 境界

- Python: camera, MediaPipe, visibility filtering, wrist speed, hip sway
- Java/Processing: OSC受信、座標変換、骨格・残像・波紋の描画
- 契約: `/pose/points`, `/left_speed`, `/right_speed`, `/hip_sway`

生映像を保存しません。OSCポート12000を他のアプリが使っていないことを確認してください。
