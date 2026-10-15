# mpp5 — Python Pose Interpreter × Multiple Renderers

ローカルカメラとMediaPipe Poseを使う身体入力のPoCです。**Pythonが姿勢・動きを一度だけ解釈し、描画先を疎結合で選べます。** 海中ゲームのp5.js表示と、Processing（Java mode）のサイケデリック投影表示を同じPythonプロセスから利用できます。

## 構成

- **Python + OpenCV + MediaPipe**: カメラ取得、姿勢推定、信頼度フィルタ、動き属性の解釈
- **FastAPI + WebSocket**: 海中ゲーム用の状態をブラウザへ配信
- **OSC / UDP**: 正規化ランドマーク、手首速度、腰の揺れ強度をProcessingへ配信
- **p5.js renderer**: イルカ、泡、海中エフェクト
- **Processing / Java renderer**: 骨格、残像、手首トレイル、腰の波紋

カメラ映像は保存・送信せず、姿勢由来の数値のみをローカル端末内で配信します。2つの描画先は同時に動作できます。

## 起動方法（Windows / PowerShell）

Python 3.11または3.12を推奨します。

```powershell
git clone https://github.com/bonsai/mpp5.git
cd mpp5
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python server.py
```

海中ゲームを表示する場合は http://127.0.0.1:8765 を開きます。

## Processing（Java）投影を使う

1. Processing 4をインストール
2. Processing IDEで **Sketch → Import Library… → Manage Libraries…** を開き、`oscP5` をインストール
3. `processing/psychedelic_pose_projection.pde` をProcessing IDEで開き、Run
4. 上記の手順で起動した `python server.py` がカメラを取得し、OSCを `127.0.0.1:12000/UDP` に送信します

または `processing/start.ps1` でProcessingスケッチを開けます。Pythonサーバーは別途起動してください。Processing側は受信した値を描画するだけで、MediaPipeや姿勢の意味解釈を行いません。

## OSC契約

| Address | Payload | 意味 |
|---|---|---|
| `/pose/points` | 14点 × (x,y)、正規化座標 | 13個のランドマーク + 腰中心 |
| `/left_speed` | float | 左手首のフレーム間移動量（px/frame） |
| `/right_speed` | float | 右手首のフレーム間移動量（px/frame） |
| `/hip_sway` | float（0〜1.5） | 腰の横揺れ強度 |

点が検出できない場合は `(-1,-1)`、人物を追跡できない場合は全属性を中立値に戻します。ポート12000を他のアプリが使っていないことを確認してください。

## 海中ゲームの操作

- 左右に体を傾ける: イルカを左右へ誘導
- 両腕を左右に広げる: 泡の輪を発生
- しゃがむ: 深海モードへ移行

## プライバシーとPoCの限界

映像はメモリ上で処理し、保存しません。ランドマーク由来の数値だけをローカルWebSocket/OSCで配信します。商用施設での運用前に、遅延、誤認識、照明・服装・距離・複数人の影響、アクセシビリティ、安全なプレイ範囲を検証してください。

## 関連リポジトリ

- [psychedelic-pose-projection](https://github.com/bonsai/psychedelic-pose-projection): 研究・評価・エフェクト設計。Javaランタイムは本リポジトリに集約
- [air-shodo](https://github.com/bonsai/air-shodo): モジュール分割と疎結合の参考
