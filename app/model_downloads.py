"""On-demand Whisper model installation shared by WebUI and ASR inference."""
from __future__ import annotations

import threading
import time

from .install_assets import WHISPER_MODELS, download_whisper_models, whisper_model_installed
from .providers import (
    _ensure_mlx_whisper_model,
    _is_apple_silicon,
    _local_mlx_whisper_path,
)

_DOWNLOAD_LOCK = threading.Lock()


def backend_for(device: str = "auto") -> str:
    if device not in {"auto", "cpu", "cuda", "apple"}:
        raise ValueError(f"Unsupported Whisper device: {device}")
    if _is_apple_silicon() and device in {"auto", "apple", "cuda"}:
        return "mlx"
    return "faster"


def validate_model(name: str) -> None:
    if name not in WHISPER_MODELS:
        raise ValueError(f"Unsupported Whisper model: {name}")


def is_model_installed(name: str, device: str = "auto") -> bool:
    validate_model(name)
    backend = backend_for(device)
    if backend == "mlx":
        return _local_mlx_whisper_path(name) is not None
    return whisper_model_installed(name)


def ensure_whisper_model(name: str, device: str = "auto") -> None:
    validate_model(name)
    backend = backend_for(device)
    if is_model_installed(name, device):
        return
    if backend == "faster":
        download_whisper_models((name,))
        return
    # MLX uses Hugging Face local_dir metadata to resume interrupted downloads.
    with _DOWNLOAD_LOCK:
        if is_model_installed(name, device):
            return
        for attempt in range(1, 4):
            try:
                _ensure_mlx_whisper_model(name)
                if not is_model_installed(name, device):
                    raise RuntimeError("MLX model files are incomplete")
                return
            except Exception as exc:
                if attempt == 3:
                    raise RuntimeError(
                        f"MLX Whisper {name} download failed after 3 attempts; retry to resume."
                    ) from exc
                print(f"[setup] MLX Whisper {name}: attempt {attempt}/3 failed: {exc}")
                time.sleep(min(2 ** attempt, 8))
