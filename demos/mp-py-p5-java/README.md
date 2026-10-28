# mp-py + p5-java デモ

MediaPipe (Python) でポーズ検出し、OSC で Processing(Java) に送って手描き風に描画する分離構成のデモ。

## 構成

```
[Webカメラ/動画] -> mp_osc_sender.py (MediaPipe Pose) --(OSC /mppose/*)--> MPPoseManga.pde (Processing + oscP5)
```

## セットアップ

### 1) Python依存

```bash
pip install -r requirements.txt
```

### 2) Processing ライブラリ

Processing を開き:
1. `Sketch > Import Library > Add Library...`
2. 検索: `oscP5` をインストール

## 起動手順

2つのターミナルで起動します。

### ターミナル1: Processing
1. Processing で `processing/MPPoseManga/MPPoseManga.pde` を開く
2. Run (▶) して 1280x720 ウィンドウを起動（9000番ポートで待受）

### ターミナル2: Python sender
```bash
# Webカメラ
python mp_osc_sender.py

# 動画ファイル
python mp_osc_sender.py --input path/to/video.mp4

# ミラー（webcam向け）
python mp_osc_sender.py --mirror
```

## 操作キー (Processing)
| キー | 説明 |
|---|---|
| `p` | 骨格表示 ON/OFF |
| `b` | boil(線の震え) ON/OFF |
| `r` | ジッターの種を再生成 |
| `s` | 現在フレームをPNG保存 |
| `ESC` | （終了防止のため無効化） |

## OSCメッセージ仕様
| アドレス | 引数 | 説明 |
|---|---|---|
| `/mppose/start` | `[time, w, h, fps]` | セッション開始 |
| `/mppose/frame` | `[frame_idx, w, h, fps_disp]` | フレーム情報 |
| `/mppose/landmark` | `[idx, x, y, z, visibility]` | 各ランドマーク (正規化) |
| `/mppose/end` | `[frame_idx, time]` | セッション終了 |
