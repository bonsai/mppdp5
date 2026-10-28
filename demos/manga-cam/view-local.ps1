# view-local.ps1 — clone してすぐ Processing 版レンダラを見る
# 使い方: PowerShell でこのファイルを実行するだけ
#   .\view-local.ps1
# やること:
#   1. bonsai/video2storyboard と bonsai/video2poses を clone (済みなら pull)
#   2. poses-0001.jsonl をスケッチの data/ にコピー
#   3. processing-java があればそのまま実行、なければ .pde を開く

$ErrorActionPreference = 'Stop'
$base = Join-Path $HOME 'bonsai-view'
New-Item -ItemType Directory -Force $base | Out-Null

function Get-Repo([string]$name) {
    $dest = Join-Path $base $name
    if (Test-Path (Join-Path $dest '.git')) {
        Write-Host "pull $name"
        git -C $dest pull --ff-only
    } else {
        Write-Host "clone $name"
        git clone "https://github.com/bonsai/$name.git" $dest
    }
}

Get-Repo 'video2storyboard'
Get-Repo 'video2poses'

$sketch = Join-Path $base 'video2storyboard\demos\manga-cam\processing\PoseRendererP5'
$dataDir = Join-Path $sketch 'data'
New-Item -ItemType Directory -Force $dataDir | Out-Null

$poses = Join-Path $base 'video2poses\projects\01-bubbly\data\gen1\poses-0001.jsonl'
Copy-Item $poses (Join-Path $dataDir 'poses-0001.jsonl') -Force
Write-Host "poses copied -> $dataDir"

$pj = Get-Command 'processing-java' -ErrorAction SilentlyContinue
if ($pj) {
    Write-Host 'launching with processing-java...'
    & processing-java --sketch="$sketch" --run
} else {
    Write-Host 'processing-java not found. Opening the sketch file instead.'
    Write-Host 'Install Processing 4 and press Run: https://processing.org/download'
    Start-Process (Join-Path $sketch 'PoseRendererP5.pde')
}
