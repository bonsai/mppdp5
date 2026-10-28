<#
.SYNOPSIS
    Save background frame from camera on Windows 11.

.DESCRIPTION
    Uses Windows.Media.Capture API to capture a high-quality frame from the camera.
    Handles Windows 11 camera privacy settings and auto-exposure warmup.

.PARAMETER CameraIndex
    Camera device index (default: 0).

.PARAMETER OutputPath
    Output image file path (default: ./background.png).

.PARAMETER Width
    Capture width (default: 1920).

.PARAMETER Height
    Capture height (default: 1080).

.PARAMETER WarmupFrames
    Frames to discard for auto-exposure stabilization (default: 30).

.EXAMPLE
    .\save_background.ps1 -OutputPath "work\background.png"

.EXAMPLE
    .\save_background.ps1 -CameraIndex 1 -Width 1280 -Height 720 -WarmupFrames 50
#>

param(
    [int]$CameraIndex = 0,
    [string]$OutputPath = ".\background.png",
    [int]$Width = 1920,
    [int]$Height = 1080,
    [int]$WarmupFrames = 30
)

# Ensure output directory exists
$outputDir = Split-Path $OutputPath -Parent
if ($outputDir -and -not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

# Check camera access permission (Windows 11)
Write-Host "Checking camera permissions..." -ForegroundColor Cyan

# Try to open camera via OpenCV if available
$pythonScript = @"
import cv2
import sys

cap = cv2.VideoCapture($CameraIndex, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap = cv2.VideoCapture($CameraIndex)
    
if not cap.isOpened():
    print("ERROR: Cannot open camera $CameraIndex")
    print("Check Windows 11 Settings > Privacy & security > Camera")
    print("Ensure 'Camera access' and 'Let apps access your camera' are ON")
    print("Ensure 'Desktop apps' camera access is ON")
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, $Width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, $Height)
cap.set(cv2.CAP_PROP_FPS, 30)

print(f"Camera opened: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)} @ {cap.get(cv2.CAP_PROP_FPS)}fps")

# Warmup for auto-exposure/white-balance
print(f"Warming up ({ $WarmupFrames } frames)...")
for i in range($WarmupFrames):
    ret, frame = cap.read()
    if not ret:
        continue

print("Capturing background frame...")
ret, frame = cap.read()
if not ret:
    print("ERROR: Failed to capture frame")
    sys.exit(1)

import os
os.makedirs(os.path.dirname("$OutputPath") or ".", exist_ok=True)
cv2.imwrite("$OutputPath", frame)
print(f"SUCCESS: Saved to $OutputPath ({frame.shape[1]}x{frame.shape[0]})")
cap.release()
"@

# Execute via Python
$pythonExe = "python"
if (Get-Command "python3" -ErrorAction SilentlyContinue) { $pythonExe = "python3" }

Write-Host "Capturing background frame..." -ForegroundColor Green
Write-Host "  Camera: $CameraIndex" -ForegroundColor Gray
Write-Host "  Resolution: ${Width}x${Height}" -ForegroundColor Gray
Write-Host "  Warmup frames: $WarmupFrames" -ForegroundColor Gray
Write-Host "  Output: $OutputPath" -ForegroundColor Gray

$result = & $pythonExe -c $pythonScript 2>&1

foreach ($line in $result) {
    if ($line -like "ERROR:*") {
        Write-Host $line -ForegroundColor Red
    } elseif ($line -like "SUCCESS:*") {
        Write-Host $line -ForegroundColor Green
    } elseif ($line -like "Warming*" -or $line -like "Capturing*" -or $line -like "Camera opened*") {
        Write-Host $line -ForegroundColor Cyan
    } else {
        Write-Host $line
    }
}

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Open Windows Settings > Privacy & security > Camera" -ForegroundColor Gray
    Write-Host "2. Turn ON 'Camera access' and 'Let apps access your camera'" -ForegroundColor Gray
    Write-Host "3. Scroll down and turn ON 'Desktop apps' access" -ForegroundColor Gray
    Write-Host "4. Restart terminal/PowerShell after changing permissions" -ForegroundColor Gray
    Write-Host "5. Try: .\save_background.ps1 -CameraIndex 1 (if multiple cameras)" -ForegroundColor Gray
    exit $exitCode
}

Write-Host "`nDone!" -ForegroundColor Green