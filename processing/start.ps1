# Open the Processing sketch; start python server.py separately from the repo root.
$ErrorActionPreference = "Stop"
$sketch = Join-Path $PSScriptRoot "psychedelic_pose_projection.pde"
if (-not (Test-Path $sketch)) { throw "Processing sketch not found: $sketch" }
$processing = Get-Command processing-java -ErrorAction SilentlyContinue
if ($processing) {
    & $processing.Source --sketch="$PSScriptRoot" --run
} else {
    Write-Host "Open this sketch in Processing 4 IDE and press Run:"
    Write-Host $sketch
    Start-Process explorer.exe $PSScriptRoot
}
