#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
export ALT_DATA_DIR="${ALT_DATA_DIR:-$ROOT/data}"
export ALT_MODELS_DIR="${ALT_MODELS_DIR:-$ROOT/models}"
export ALT_CACHE_DIR="${ALT_CACHE_DIR:-$ROOT/cache}"
export ALT_LOGS_DIR="${ALT_LOGS_DIR:-$ROOT/logs}"
export HF_HOME="${HF_HOME:-$ROOT/cache/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export HF_XET_CACHE="${HF_XET_CACHE:-$HF_HOME/xet}"
export HF_ASSETS_CACHE="${HF_ASSETS_CACHE:-$HF_HOME/assets}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$ROOT/cache/pip}"
export TMPDIR="${TMPDIR:-$ROOT/cache/temp}"
mkdir -p "$ALT_DATA_DIR" "$ALT_MODELS_DIR" "$ALT_CACHE_DIR" "$ALT_LOGS_DIR" "$HF_HOME" "$PIP_CACHE_DIR" "$TMPDIR"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  PYTHON_ARCH="$(.venv/bin/python -c 'import platform; print(platform.machine())')"
  if [[ "$PYTHON_ARCH" != "arm64" ]]; then
    echo "[setup] This Mac has Apple silicon, but the selected Python is running as $PYTHON_ARCH. Install a native arm64 Python and remove .venv before retrying."
    exit 1
  fi
fi
.venv/bin/python -m pip install --disable-pip-version-check --upgrade pip
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
if [[ "$(uname -s)" == "Darwin" ]]; then
  .venv/bin/python -m app.install_assets
else
  .venv/bin/python -m app.bootstrap
fi
echo "[start] Academic Live Translator beta 0.9 -> http://127.0.0.1:8765"
.venv/bin/python run.py
