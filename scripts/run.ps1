param(
    [string]$ListenAddr = "0.0.0.0",
    [int]$Port = 80,
    [switch]$Reload = $true
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Check for bundled binaries
if (-not (Test-Path "ffmpeg.exe")) { Write-Warning "ffmpeg.exe not found" }
if (-not (Test-Path "aria2c.exe")) { Write-Warning "aria2c.exe not found" }

# Try to find Python 3.11+ (deps installed there)
$PythonExe = $null
$candidates = @(
    "C:\Users\Rfan\AppData\Local\Programs\Python\Python311\python.exe",
    "C:\Python311\python.exe",
    (Get-Command "python3" -ErrorAction SilentlyContinue).Source,
    (Get-Command "python" -ErrorAction SilentlyContinue).Source
)
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) {
        try {
            $v = & $c -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ([version]$v -ge [version]"3.10") { $PythonExe = $c; break }
        } catch {}
    }
}

if (-not $PythonExe) { Write-Error "Python 3.10+ not found"; exit 1 }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  OpenPlex Server (Windows)" -ForegroundColor Cyan
Write-Host "  Python: $PythonExe" -ForegroundColor Cyan
Write-Host "  URL:    http://$ListenAddr`:$Port" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$reloadFlag = if ($Reload) { "--reload" } else { "" }
& $PythonExe -m uvicorn app.main:app --host $ListenAddr --port $Port $reloadFlag
