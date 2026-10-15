# Open or run the correctly named Processing sketch folder.
$ErrorActionPreference = "Stop"
$sketchDir = Join-Path $PSScriptRoot "psychedelic_pose_projection"
$sketch = Join-Path $sketchDir "psychedelic_pose_projection.pde"
if (-not (Test-Path $sketch)) { throw "Processing sketch not found: $sketch" }
$processing = Get-Command processing-java -ErrorAction SilentlyContinue
if ($processing) {
    & $processing.Source --sketch="$sketchDir" --run
} else {
    Write-Host "Open this sketch in Processing 4 IDE and press Run:"
    Write-Host $sketch
    Start-Process explorer.exe $sketchDir
}
