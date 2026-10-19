"""Install platform-specific Whisper models and optional GPU runtimes."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .audio import pcm16_to_wav_bytes
from .config import CACHE_DIR, DATA_DIR, MODELS_DIR, PROJECT_ROOT, load_config
from .models import ProviderConfig
from .providers import MLX_WHISPER_REPOS, _ensure_mlx_whisper_model, _is_apple_silicon, _local_whisper_transcribe

WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3-turbo")
CUDA_RUNTIME_URL = (
    "https://github.com/Purfview/whisper-standalone-win/releases/download/libs/"
    "cuBLAS.and.cuDNN_CUDA12_win_v3.7z"
)
RUNTIME_DIR = PROJECT_ROOT / "runtime"
CUDA_BIN = RUNTIME_DIR / "cuda12" / "bin"
INSTALL_MARKER = DATA_DIR / ".installed-lite-1.0"
_DLL_HANDLES: list[object] = []
_MODEL_DOWNLOAD_LOCK = threading.Lock()


def _has_nvidia_gpu() -> bool:
    if sys.platform != "win32":
        return False
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False
    try:
        result = subprocess.run([exe, "-L"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and "GPU" in result.stdout
    except Exception:
        return False


def _progress(blocks: int, block_size: int, total: int) -> None:
    if total <= 0:
        return
    current = min(total, blocks * block_size)
    percent = current * 100 / total
    print(f"\r[setup] CUDA runtime download: {percent:5.1f}%", end="", flush=True)
    if current >= total:
        print()


def _activate_cuda_runtime() -> None:
    if sys.platform != "win32" or not CUDA_BIN.exists():
        return
    os.environ["PATH"] = str(CUDA_BIN) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        _DLL_HANDLES.append(os.add_dll_directory(str(CUDA_BIN)))


def _extract_cuda_archive(archive: Path, destination: Path) -> None:
    if sys.platform == "win32":
        windows_tar = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "tar.exe"
        if not windows_tar.exists():
            raise RuntimeError("Windows tar.exe is required to extract the CUDA runtime archive")
        result = subprocess.run(
            [str(windows_tar), "-xf", str(archive), "-C", str(destination)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                f"Windows tar.exe could not extract the CUDA runtime archive "
                f"(exit code {result.returncode}): {detail}"
            )
        return

    import py7zr

    with py7zr.SevenZipFile(archive, mode="r") as seven:
        seven.extractall(path=destination)


def whisper_model_installed(model_name: str) -> bool:
    """Check required files before advertising a model as installed."""
    if model_name not in WHISPER_MODELS:
        return False
    folder = MODELS_DIR / "faster-whisper" / model_name
    weights = folder / "model.bin"
    if not weights.is_file() or weights.stat().st_size < 1_000_000:
        return False
    for name in ("config.json", "tokenizer.json"):
        path = folder / name
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            with path.open("r", encoding="utf-8") as stream:
                if not isinstance(json.load(stream), dict):
                    return False
        except (ValueError, OSError, UnicodeError):
            return False
    return True


def _fetch_whisper_model(model_name: str, destination: Path) -> None:
    from faster_whisper.utils import download_model

    # The Hugging Face local_dir metadata and .incomplete files are retained
    # between attempts, so the Hub downloader can reuse already fetched bytes.
    download_model(model_name, output_dir=str(destination), cache_dir=str(CACHE_DIR / "huggingface"))


def download_whisper_models(model_names: tuple[str, ...] = ("base",)) -> None:
    root = MODELS_DIR / "faster-whisper"
    root.mkdir(parents=True, exist_ok=True)
    for name in model_names:
        if name not in WHISPER_MODELS:
            raise ValueError(f"Unsupported Whisper model: {name}")
        with _MODEL_DOWNLOAD_LOCK:
            if whisper_model_installed(name):
                print(f"[setup] Whisper {name}: already installed")
                continue
            destination = root / name
            destination.mkdir(parents=True, exist_ok=True)
            for attempt in range(1, 4):
                print(f"[setup] Whisper {name}: downloading/resuming (attempt {attempt}/3)...")
                try:
                    _fetch_whisper_model(name, destination)
                    if not whisper_model_installed(name):
                        raise RuntimeError("model.bin / config.json / tokenizer.json missing or invalid")
                    print(f"[setup] Whisper {name}: verified and ready")
                    break
                except Exception as exc:
                    print(f"[setup] Whisper {name}: {exc}")
                    if attempt == 3:
                        raise RuntimeError(
                            f"Whisper {name} could not be downloaded after 3 attempts. "
                            "Run the installer again to reuse the partial download."
                        ) from exc
                    time.sleep(min(2 ** attempt, 8))

def _download_cuda_archive(url: str, archive: Path) -> None:
    """Stream to a .part file and resume with HTTP Range when supported."""
    partial = archive.with_name(archive.name + ".part")
    for attempt in range(1, 4):
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                status = getattr(response, "status", response.getcode())
                append = existing > 0 and status == 206
                if append:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {existing}-"):
                        raise RuntimeError("Server returned an invalid resume range")
                else:
                    existing = 0  # Server ignored Range: restart safely, no duplicate bytes.
                remaining = int(response.headers.get("Content-Length", "0"))
                total = existing + remaining if remaining else 0
                with partial.open("ab" if append else "wb") as output:
                    current = existing
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        current += len(chunk)
                        if total:
                            print(f"\r[setup] CUDA runtime download: {current * 100 / total:5.1f}%", end="", flush=True)
                if total and current != total:
                    raise IOError(f"Incomplete CUDA runtime download ({current}/{total} bytes)")
            if total:
                print()
            partial.replace(archive)
            return
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and partial.exists():
                # The partial file may already be complete. Extraction verifies it.
                partial.replace(archive)
                return
            print(f"\n[setup] CUDA download attempt {attempt}/3 failed: {exc}")
            if attempt == 3:
                raise RuntimeError("CUDA runtime download failed; retry installation to resume.") from exc
            time.sleep(min(2 ** attempt, 8))
        except Exception as exc:
            print(f"\n[setup] CUDA download attempt {attempt}/3 failed: {exc}")
            if attempt == 3:
                raise RuntimeError("CUDA runtime download failed; retry installation to resume.") from exc
            time.sleep(min(2 ** attempt, 8))


def download_cuda_runtime() -> bool:
    if sys.platform != "win32":
        print("[setup] CUDA runtime: skipped (Windows-only portable package)")
        return False
    if not _has_nvidia_gpu():
        print("[setup] CUDA runtime: NVIDIA GPU not detected; CPU runtime is ready via CTranslate2")
        return False
    required = (CUDA_BIN / "cublas64_12.dll", CUDA_BIN / "cudnn64_9.dll")
    if all(path.exists() and path.stat().st_size > 0 for path in required):
        print("[setup] CUDA 12 cuBLAS/cuDNN runtime: already installed")
        _activate_cuda_runtime()
        return True

    downloads = CACHE_DIR / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / "cuBLAS.and.cuDNN_CUDA12_win_v3.7z"
    CUDA_BIN.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 3):
        if not archive.exists():
            print("[setup] NVIDIA GPU detected; downloading/resuming CUDA runtime...")
            _download_cuda_archive(CUDA_RUNTIME_URL, archive)
        try:
            with tempfile.TemporaryDirectory(prefix="alt-cuda-", dir=str(CACHE_DIR / "temp")) as temp_dir:
                temp = Path(temp_dir)
                print("[setup] Extracting portable CUDA runtime...")
                _extract_cuda_archive(archive, temp)
                dlls = list(temp.rglob("*.dll"))
                names = {p.name for p in dlls}
                if not {"cublas64_12.dll", "cudnn64_9.dll"}.issubset(names):
                    raise RuntimeError("CUDA archive is missing required DLL files")
                for source in dlls:
                    shutil.copy2(source, CUDA_BIN / source.name)
            break
        except Exception as exc:
            print(f"[setup] CUDA archive invalid: {exc}")
            archive.unlink(missing_ok=True)
            if attempt == 2:
                raise RuntimeError("CUDA runtime extraction failed after redownload") from exc

    (CUDA_BIN.parent / "SOURCE.txt").write_text(
        "Faster-Whisper Windows CUDA runtime bundle\n"
        f"Source: {CUDA_RUNTIME_URL}\n",
        encoding="utf-8",
    )
    _activate_cuda_runtime()
    if not all(path.exists() and path.stat().st_size > 0 for path in required):
        raise RuntimeError("Portable CUDA runtime extraction is incomplete")
    print(f"[setup] CUDA runtime: ready in {CUDA_BIN}")
    return True

def _consume(generator) -> None:
    list(generator)


def self_test(cuda_installed: bool, model_name: str = "tiny") -> None:
    import numpy as np
    from faster_whisper import WhisperModel

    model_path = MODELS_DIR / "faster-whisper" / model_name
    silence = np.zeros(16000, dtype=np.float32)

    print("[setup] Self-test: Whisper CPU / int8 ...")
    cpu = WhisperModel(str(model_path), device="cpu", compute_type="int8")
    segments, _ = cpu.transcribe(silence, language="en", beam_size=1, best_of=1)
    _consume(segments)
    del cpu
    print("[setup] Self-test: Whisper CPU OK")

    if cuda_installed:
        print("[setup] Self-test: Whisper CUDA / float16 ...")
        try:
            gpu = WhisperModel(str(model_path), device="cuda", compute_type="float16")
            segments, _ = gpu.transcribe(silence, language="en", beam_size=1, best_of=1)
            _consume(segments)
            del gpu
            print("[setup] Self-test: Whisper CUDA OK")
        except Exception as exc:
            raise RuntimeError(f"CUDA Whisper inference self-test failed: {exc}") from exc


def self_test_apple_silicon(model_name: str) -> None:
    if not _is_apple_silicon():
        raise RuntimeError("Apple silicon setup was selected on a non-Apple-silicon Python runtime")
    silence = pcm16_to_wav_bytes(b"\x00\x00" * 16000, 16000)
    for device in ("cpu", "apple"):
        cfg = ProviderConfig(model=model_name, device=device, compute_type="auto")
        label = "CPU / int8" if device == "cpu" else "Apple GPU / MLX"
        print(f"[setup] Self-test: Whisper {label} ...")
        try:
            _local_whisper_transcribe(silence, cfg, "en", "")
        except Exception as exc:
            raise RuntimeError(f"Whisper {label} inference self-test failed: {exc}") from exc
        print(f"[setup] Self-test: Whisper {label} OK")


def _installation_is_current() -> bool:
    try:
        return INSTALL_MARKER.read_text(encoding="utf-8").strip() == "1.0-lite"
    except OSError:
        return False


def main() -> None:
    (CACHE_DIR / "temp").mkdir(parents=True, exist_ok=True)
    if _installation_is_current():
        print("[setup] 1.0 lightweight platform assets are already installed")
        return

    cfg = load_config()
    print("[setup] Academic Live Translator 1.0 lightweight platform setup")
    if sys.platform == "win32":
        print("[setup] CPU runtime is provided by CTranslate2; checking optional NVIDIA CUDA runtime.")
        if cfg.asr.mode == "local_whisper":
            download_whisper_models((cfg.asr.model,))
            cuda_installed = download_cuda_runtime()
            self_test(cuda_installed, cfg.asr.model)
        else:
            print("[setup] External ASR configured; local models and CUDA are skipped.")
    elif cfg.asr.mode != "local_whisper":
        print("[setup] External ASR is configured; local Whisper model setup is skipped.")
    elif _is_apple_silicon():
        if cfg.asr.model not in MLX_WHISPER_REPOS:
            raise RuntimeError(f"Unsupported Whisper model selected: {cfg.asr.model}")
        print("[setup] Apple silicon detected; preparing MLX/Metal and CPU Whisper runtimes.")
        download_whisper_models((cfg.asr.model,))
        _ensure_mlx_whisper_model(cfg.asr.model)
        self_test_apple_silicon(cfg.asr.model)
    else:
        print("[setup] Preparing the CPU Whisper runtime for this platform.")
        download_whisper_models((cfg.asr.model,))
        cpu_cfg = ProviderConfig(model=cfg.asr.model, device="cpu", compute_type="auto")
        silence = pcm16_to_wav_bytes(b"\x00\x00" * 16000, 16000)
        _local_whisper_transcribe(silence, cpu_cfg, "en", "")

    INSTALL_MARKER.write_text("1.0-lite\n", encoding="utf-8")
    print("[setup] Portable installation complete.")


if __name__ == "__main__":
    main()
