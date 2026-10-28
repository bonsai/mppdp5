# run_demo.ps1
# mp-py + p5-java demo launcher

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  mp-py + p5-java Demo Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found in PATH" -ForegroundColor Red
    exit 1
}

# Check requirements
Write-Host ""
Write-Host "Checking Python dependencies..." -ForegroundColor Yellow
$requirements = @("opencv-python", "mediapipe", "python-osc", "numpy")
$missing = @()

foreach ($req in $requirements) {
    $pkgName = $req.Split("==")[0].Split(">=")[0].Split("<=")[0]
    $installed = pip show $pkgName 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missing += $req
        Write-Host "  [MISSING] $pkgName" -ForegroundColor Red
    } else {
        Write-Host "  [OK] $pkgName" -ForegroundColor Green
    }
}

# Install if missing
if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing packages: $($missing -join ', ')" -ForegroundColor Yellow
    $install = Read-Host "Install missing packages? (y/N)"
    if ($install -eq 'y' -or $install -eq 'Y') {
        Write-Host "Installing packages..." -ForegroundColor Yellow
        pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to install packages" -ForegroundColor Red
            exit 1
        }
        Write-Host "[OK] Packages installed" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] Some packages missing. Demo may not work." -ForegroundColor Yellow
    }
}

# Check Processing
Write-Host ""
Write-Host "Checking Processing..." -ForegroundColor Yellow
$processingPaths = @(
    "C:\Program Files\processing-*\processing.exe",
    "C:\Program Files (x86)\processing-*\processing.exe",
    "$env:LOCALAPPDATA\processing-*\processing.exe",
    "$env:USERPROFILE\processing-*\processing.exe"
)

$processingFound = $null
foreach ($path in $processingPaths) {
    $found = Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $processingFound = $found.FullName
        break
    }
}

if ($processingFound) {
    Write-Host "  [OK] Processing found: $processingFound" -ForegroundColor Green
} else {
    Write-Host "  [NOT FOUND] Processing IDE not found in common locations" -ForegroundColor Yellow
    Write-Host "  You'll need to manually open: $scriptDir\processing\MPPoseManga\MPPoseManga.pde" -ForegroundColor Yellow
}

# Check oscP5 library
Write-Host ""
Write-Host "Note: oscP5 library required for Processing" -ForegroundColor Yellow
Write-Host "  Install via: Sketch > Import Library > Add Library... > search 'oscP5'" -ForegroundColor Gray

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Startup Instructions" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Open Processing and run:" -ForegroundColor White
Write-Host "   $scriptDir\processing\MPPoseManga\MPPoseManga.pde" -ForegroundColor Gray
Write-Host "   (It will listen on OSC port 9000)" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Start the MediaPipe sender in this window" -ForegroundColor White
Write-Host ""

$startSender = Read-Host "Start sender now? (y/N)"
if ($startSender -eq 'y' -or $startSender -eq 'Y') {
    Write-Host ""
    Write-Host "Starting mp_osc_sender.py..." -ForegroundColor Green
    Write-Host "Press 'q' in the sender window to quit" -ForegroundColor Gray
    Write-Host ""
    
    $mirror = Read-Host "Use mirror mode for webcam? (Y/n)"
    if ($mirror -eq 'n' -or $mirror -eq 'N') {
        python mp_osc_sender.py
    } else {
        python mp_osc_sender.py --mirror
    }
} else {
    Write-Host ""
    Write-Host "To start sender manually:" -ForegroundColor Yellow
    Write-Host "  python mp_osc_sender.py --mirror" -ForegroundColor Gray
    Write-Host "  or" -ForegroundColor Gray
    Write-Host "  python mp_osc_sender.py --input <video.mp4>" -ForegroundColor Gray
}
