$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:ALT_DATA_DIR = Join-Path $PSScriptRoot "data"
$env:ALT_MODELS_DIR = Join-Path $PSScriptRoot "models"
$env:ALT_CACHE_DIR = Join-Path $PSScriptRoot "cache"
$env:ALT_LOGS_DIR = Join-Path $PSScriptRoot "logs"
$env:ALT_RUNTIME_DIR = Join-Path $PSScriptRoot "runtime"
$env:HF_HOME = Join-Path $PSScriptRoot "cache\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:HF_XET_CACHE = Join-Path $env:HF_HOME "xet"
$env:HF_ASSETS_CACHE = Join-Path $env:HF_HOME "assets"
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot "cache\pip"
$env:TEMP = Join-Path $PSScriptRoot "cache\temp"
$env:TMP = $env:TEMP

@($env:ALT_DATA_DIR, $env:ALT_MODELS_DIR, $env:ALT_CACHE_DIR, $env:ALT_LOGS_DIR, $env:ALT_RUNTIME_DIR, $env:HF_HOME, $env:PIP_CACHE_DIR, $env:TEMP) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

$cudaBin = Join-Path $PSScriptRoot "runtime\cuda12\bin"
if (Test-Path $cudaBin) {
    $env:PATH = "$cudaBin;$env:PATH"
}

# 1.0 changes application logic only; the existing beta 0.6 portable
# runtime bundle remains valid and should not be downloaded again.
$marker = Join-Path $PSScriptRoot "data\.installed-beta-0.6"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $marker) -or -not (Test-Path $venvPython)) {
    Write-Host "[setup] Portable runtime assets are missing; running one-click installation..."
    & (Join-Path $PSScriptRoot "install.ps1")
}
if (-not (Test-Path $marker)) {
    throw "Portable installation failed; refusing to start before runtime setup is complete."
}

if (-not (Test-Path $venvPython)) {
    throw "Portable Python environment was not created successfully."
}

Write-Host "[start] Academic Live Translator 1.0 -> http://127.0.0.1:8765"
Start-Process "http://127.0.0.1:8765"
& $venvPython run.py