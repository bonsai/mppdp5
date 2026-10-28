# MPPoseManga.pde 構造・フロー図

## 構造図 (Class/Structure)
![Java Structure](java-structure.puml)

[PlantUML](./java-structure.puml)

## フロー図 (Execution Flow)
![Java Flow](java-flow.puml)

[PlantUML](./java-flow.puml)

## 主要な変更点（最新版）
- `draw()` で `drawMangaPose()` を**無条件**に呼び出し
- `drawMangaPose()` で **visibility チェック削除**、全33ランドマーク・全接続を描画
- `wobbleAmp = 3.4`、ジッター強度 `wobbleAmp * 2.0`
- 線幅: `map(pass, 0, 3, 6.0, 2.8)`（太く描画）
- 関節: `ellipse(p.x+jx, p.y+jy, 9, 9)`
- `oscEvent()`: `/mppose/start` / `/mppose/end` で `hasPose` を落とさない
- HUD に `hasPose` を赤字で表示
