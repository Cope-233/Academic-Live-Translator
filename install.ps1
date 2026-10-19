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

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    throw "Python 3.11-3.13 was not found. Install Python or Conda and make sure 'python' is available."
}

$python = Get-PythonCommand
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[setup] Creating project-local Python environment (.venv)..."
    & $python -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Write-Host "[setup] Installing Python dependencies..."
& $venvPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip (exit code $LASTEXITCODE)." }
& $venvPython -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install Python dependencies (exit code $LASTEXITCODE)." }

Write-Host "[setup] Preparing the selected Whisper model and portable runtime files..."
& $venvPython -m app.install_assets
if ($LASTEXITCODE -ne 0) { throw "Portable model/runtime installation failed (exit code $LASTEXITCODE)." }
if (-not (Test-Path (Join-Path $PSScriptRoot "data\.installed-lite-1.0"))) {
    throw "Portable installation did not create the lightweight 1.0 completion marker."
}

Write-Host ""
Write-Host "[done] Academic Live Translator 1.0 is installed."
Write-Host "[done] Models: .\models\faster-whisper\"
Write-Host "[done] CUDA runtime (when NVIDIA is detected): .\runtime\cuda12\bin\"
Write-Host "[done] Start with start_webui.bat or start_webui.ps1"
