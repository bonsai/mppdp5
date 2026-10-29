# Install and configure bonsai/mppdp5 mediapipe-py-mcp on Windows.
# Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File .\mediapipe-py-mcp\scripts\install-windows.ps1
# Optional: skip the pose model download (when it is already present):
#   .\mediapipe-py-mcp\scripts\install-windows.ps1 -SkipModelDownload

[CmdletBinding()]
param(
    [switch]$SkipModelDownload
)

$ErrorActionPreference = 'Stop'

function Say([string]$Message) {
    Write-Host "[ mediapipe-py-mcp ] $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    throw "[ mediapipe-py-mcp ] ERROR: $Message"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$mcpDir = (Resolve-Path (Join-Path $scriptDir '..')).Path
$venvDir = Join-Path $mcpDir '.venv'
# Written inside the package so it cannot clobber puredata-mcp's repo-root config.
$configOut = Join-Path $mcpDir 'mcp-config.windows.json'
$mediaRoot = Join-Path $mcpDir 'media'
$modelsDir = Join-Path $mcpDir 'models'
$modelPath = Join-Path $modelsDir 'pose_landmarker_lite.task'
$modelUrl = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task'

$pythonCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $pythonExe = $pythonCommand.Source
    $pythonArgs = @('-3')
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        Fail 'Python 3.11+ was not found. Install Python from https://www.python.org/downloads/windows/ and enable the PATH option.'
    }
    $pythonExe = $pythonCommand.Source
    $pythonArgs = @()
}

$versionOutput = & $pythonExe @pythonArgs -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
if ($LASTEXITCODE -ne 0) { Fail 'Could not run Python.' }
$versionParts = $versionOutput.Trim().Split('.')
if ([int]$versionParts[0] -lt 3 -or ([int]$versionParts[0] -eq 3 -and [int]$versionParts[1] -lt 11)) {
    Fail "Python 3.11+ is required; detected $versionOutput."
}
Say "Python $versionOutput detected."

if (-not (Test-Path (Join-Path $mcpDir 'pyproject.toml'))) {
    Fail "pyproject.toml not found at $mcpDir. Run this script from a complete repository checkout."
}

if (Test-Path $venvDir) {
    Say "Reusing existing virtual environment: $venvDir"
} else {
    Say "Creating virtual environment: $venvDir"
    & $pythonExe @pythonArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the virtual environment.' }
}

$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$mcpExe = Join-Path $venvDir 'Scripts\mediapipe-py-mcp.exe'
if (-not (Test-Path $venvPython)) { Fail "Virtual environment Python not found: $venvPython" }

Say 'Installing/updating mediapipe-py-mcp and its dependencies.'
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail 'pip upgrade failed.' }
& $venvPython -m pip install -e $mcpDir
if ($LASTEXITCODE -ne 0) { Fail 'mediapipe-py-mcp installation failed.' }

Say 'Checking MediaPipe and the Tasks API.'
& $venvPython -c 'import mediapipe as mp; from mediapipe.tasks.python import vision; print("mediapipe", mp.__version__, "/ Tasks API OK")'
if ($LASTEXITCODE -ne 0) { Fail 'MediaPipe or the Tasks API import failed.' }

Say 'Checking MCP module import.'
& $venvPython -c 'import mediapipe_py_mcp.server; print("MCP module OK")'
if ($LASTEXITCODE -ne 0) { Fail 'MCP module import failed.' }

if (-not (Test-Path $mediaRoot)) {
    Say "Creating media root: $mediaRoot"
    New-Item -ItemType Directory -Path $mediaRoot | Out-Null
}

if ($SkipModelDownload) {
    Say 'Skipping pose model download (-SkipModelDownload).'
} elseif (Test-Path $modelPath) {
    Say "Pose model already present: $modelPath"
} else {
    if (-not (Test-Path $modelsDir)) { New-Item -ItemType Directory -Path $modelsDir | Out-Null }
    Say "Downloading pose model: $modelUrl"
    try {
        Invoke-WebRequest -Uri $modelUrl -OutFile $modelPath -UseBasicParsing
    } catch {
        Fail "Could not download the pose model: $($_.Exception.Message)"
    }
    if ((Get-Item $modelPath).Length -lt 1MB) {
        Fail "Downloaded pose model looks incomplete: $modelPath"
    }
}
if (Test-Path $modelPath) {
    Say "Pose model ready: $((Get-Item $modelPath).Length) bytes"
} else {
    Write-Warning "Pose model missing at $modelPath. mp_status will report model_present=false until it is downloaded."
}

$config = @{
    mcpServers = @{
        'mediapipe-py-mcp' = @{
            command = $mcpExe
            args = @()
            env = @{
                MP_MEDIA_ROOT = $mediaRoot
                MP_MODEL_PATH = $modelPath
                MP_OSC_HOST = '127.0.0.1'
                MP_OSC_PORT = '12000'
            }
        }
    }
}
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configOut -Encoding utf8

Say "MCP client config written: $configOut"
Write-Host ''
Write-Host 'Next steps:'
Write-Host "  1. Drop pose photos into: $mediaRoot"
Write-Host "  2. Add the contents of $configOut to your MCP client configuration."
Write-Host '     opencode uses "type": "local" and a single "command" array (no args/env split).'
Write-Host '  3. Restart the MCP client and call mp_status to confirm model_present=true.'
Write-Host '  4. mp_analyze_image needs consecutive frames for speed/sway; use mp_analyze_frame for those.'
Write-Host '  5. Windows and WSL2 are separate environments: this Windows config runs the MCP server on Windows too.'

Say 'Setup finished.'
