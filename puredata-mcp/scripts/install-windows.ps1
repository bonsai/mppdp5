# Install and configure bonsai/mppdp5 puredata-mcp on Windows.
# Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File .\puredata-mcp\scripts\install-windows.ps1
# Optional: start the Pd patch after setup:
#   .\puredata-mcp\scripts\install-windows.ps1 -LaunchPd

[CmdletBinding()]
param(
    [switch]$LaunchPd
)

$ErrorActionPreference = 'Stop'

function Say([string]$Message) {
    Write-Host "[ puredata-mcp ] $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    throw "[ puredata-mcp ] ERROR: $Message"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$mcpDir = (Resolve-Path (Join-Path $scriptDir '..')).Path
$repoRoot = (Resolve-Path (Join-Path $mcpDir '..')).Path
$venvDir = Join-Path $mcpDir '.venv'
$configOut = Join-Path $repoRoot 'mcp-config.windows.json'
$patchPath = Join-Path $mcpDir 'pd\main.pd'
$songRoot = Join-Path $mcpDir 'songs'

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
$pdCommand = Get-Command pd -ErrorAction SilentlyContinue
$pdExe = $null
if ($pdCommand) {
    $pdExe = $pdCommand.Source
} else {
    $commonPdPaths = @(
        (Join-Path $env:ProgramFiles 'Pd\bin\pd.exe'),
        (Join-Path $env:ProgramFiles 'Pure Data\bin\pd.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Pd\bin\pd.exe')
    )
    $pdExe = $commonPdPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $pdExe) {
    Write-Warning 'Pure Data (pd.exe) was not found on PATH or in common install locations. Install it from https://puredata.info/downloads/pure-data, then rerun this script.'
} else {
    Say "Pure Data detected: $pdExe"
    try {
        $pdVersion = & $pdExe -version 2>&1 | Select-Object -First 1
        Say "Pure Data version check returned: $pdVersion"
    } catch {
        Write-Warning "Could not query Pd version; the executable was found at $pdExe"
    }
}

if (-not (Test-Path (Join-Path $mcpDir 'pyproject.toml'))) {
    Fail "pyproject.toml not found at $mcpDir. Run this script from a complete repository checkout."
}
if (-not (Test-Path $patchPath)) { Fail "Pd patch not found: $patchPath" }

if (Test-Path $venvDir) {
    Say "Reusing existing virtual environment: $venvDir"
} else {
    Say "Creating virtual environment: $venvDir"
    & $pythonExe @pythonArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the virtual environment.' }
}

$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$mcpExe = Join-Path $venvDir 'Scripts\puredata-mcp.exe'
if (-not (Test-Path $venvPython)) { Fail "Virtual environment Python not found: $venvPython" }

Say 'Installing/updating puredata-mcp and its dependencies.'
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail 'pip upgrade failed.' }
& $venvPython -m pip install -e $mcpDir
if ($LASTEXITCODE -ne 0) { Fail 'puredata-mcp installation failed.' }

Say 'Checking MCP module import.'
& $venvPython -c 'import puredata_mcp.server; print("MCP module OK")'
if ($LASTEXITCODE -ne 0) { Fail 'MCP module import failed.' }

$config = @{
    mcpServers = @{
        'puredata-mcp' = @{
            command = $mcpExe
            args = @()
            env = @{
                PD_OSC_HOST = '127.0.0.1'
                PD_OSC_PORT = '9000'
                PD_SONG_ROOT = $songRoot
            }
        }
    }
}
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configOut -Encoding utf8

Say "MCP client config written: $configOut"
Write-Host ''
Write-Host 'Next steps:'
Write-Host "  1. Open the Pd patch: $patchPath"
Write-Host "  2. Add the contents of $configOut to your MCP client configuration."
Write-Host '  3. Restart the MCP client and test the puredata-mcp tools.'
Write-Host '  4. The current Pd patch is an initial scaffold; receiving a UDP packet does not prove audio output.'
Write-Host '  5. Windows and WSL2 are separate environments: this Windows config runs the MCP server on Windows too.'

if ($LaunchPd) {
    if (-not $pdExe) {
        Write-Warning 'Cannot launch Pd because pd.exe was not found.'
    } else {
        Say 'Launching Pure Data patch.'
        Start-Process -FilePath $pdExe -ArgumentList @($patchPath)
    }
}

Say 'Setup finished.'
