"""Offline tests for lightweight installation and resumable model downloads."""
import asyncio
import io
import json

from app import install_assets, main, model_downloads
from app.models import AppConfig


def _write_model(folder):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "model.bin").open("wb") as stream:
        stream.truncate(1_000_001)
    (folder / "config.json").write_text(json.dumps({"model_type": "whisper"}), encoding="utf-8")
    (folder / "tokenizer.json").write_text(json.dumps({"model": {}}), encoding="utf-8")


def test_only_selected_model_is_installed_on_windows(monkeypatch, tmp_path):
    installed = []
    checked = []
    monkeypatch.setattr(install_assets.sys, "platform", "win32")
    monkeypatch.setattr(install_assets, "_installation_is_current", lambda: False)
    monkeypatch.setattr(install_assets, "load_config", lambda: AppConfig())
    monkeypatch.setattr(install_assets, "download_whisper_models", lambda names: installed.extend(names))
    monkeypatch.setattr(install_assets, "download_cuda_runtime", lambda: False)
    monkeypatch.setattr(install_assets, "self_test", lambda cuda, model: checked.append((cuda, model)))
    monkeypatch.setattr(install_assets, "INSTALL_MARKER", tmp_path / "marker")

    install_assets.main()

    assert installed == ["base"]
    assert checked == [(False, "base")]
    assert (tmp_path / "marker").read_text(encoding="utf-8").strip() == "1.0-lite"


def test_model_integrity_requires_config_tokenizer_and_weights(monkeypatch, tmp_path):
    monkeypatch.setattr(install_assets, "MODELS_DIR", tmp_path)
    folder = tmp_path / "faster-whisper" / "base"
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"truncated")
    assert not install_assets.whisper_model_installed("base")
    _write_model(folder)
    assert install_assets.whisper_model_installed("base")
    (folder / "tokenizer.json").write_text("broken", encoding="utf-8")
    assert not install_assets.whisper_model_installed("base")


def test_failed_whisper_download_retries_and_reuses_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(install_assets, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(install_assets.time, "sleep", lambda _: None)
    attempts = []

    def fake_fetch(name, destination):
        attempts.append((name, destination))
        if len(attempts) == 1:
            (destination / "partial.marker").write_text("reused", encoding="utf-8")
            raise OSError("connection dropped")
        assert (destination / "partial.marker").read_text(encoding="utf-8") == "reused"
        _write_model(destination)

    monkeypatch.setattr(install_assets, "_fetch_whisper_model", fake_fetch)
    install_assets.download_whisper_models(("base",))
    assert len(attempts) == 2
    install_assets.download_whisper_models(("base",))
    assert len(attempts) == 2


def test_cuda_download_resumes_partial_file(monkeypatch, tmp_path):
    archive = tmp_path / "cuda.7z"
    (tmp_path / "cuda.7z.part").write_bytes(b"abc")

    class Response(io.BytesIO):
        status = 206
        headers = {"Content-Length": "4", "Content-Range": "bytes 3-6/7"}

        def getcode(self):
            return self.status

    def fake_urlopen(request, timeout):
        assert request.get_header("Range") == "bytes=3-"
        assert timeout == 45
        return Response(b"defg")

    monkeypatch.setattr(install_assets.urllib.request, "urlopen", fake_urlopen)
    install_assets._download_cuda_archive("https://example.invalid/runtime", archive)
    assert archive.read_bytes() == b"abcdefg"
    assert not (tmp_path / "cuda.7z.part").exists()


def test_cuda_ignoring_range_restarts_instead_of_appending(monkeypatch, tmp_path):
    archive = tmp_path / "cuda.7z"
    (tmp_path / "cuda.7z.part").write_bytes(b"old")

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Length": "3"}

        def getcode(self):
            return self.status

    monkeypatch.setattr(install_assets.urllib.request, "urlopen", lambda *args, **kwargs: Response(b"new"))
    install_assets._download_cuda_archive("https://example.invalid/runtime", archive)
    assert archive.read_bytes() == b"new"


def test_model_backend_selection_and_input_validation(monkeypatch):
    monkeypatch.setattr(model_downloads, "_is_apple_silicon", lambda: True)
    assert model_downloads.backend_for("auto") == "mlx"
    assert model_downloads.backend_for("cpu") == "faster"
    assert model_downloads.backend_for("cuda") == "mlx"
    try:
        model_downloads.validate_model("../../bad")
        assert False, "invalid models must be rejected"
    except ValueError:
        pass


def test_webui_model_download_job_finishes(monkeypatch):
    from app import main as application

    installed = set()
    application._WHISPER_DOWNLOAD_JOBS.clear()
    monkeypatch.setattr(application, "is_model_installed", lambda name, device: name in installed)
    monkeypatch.setattr(application, "ensure_whisper_model", lambda name, device: installed.add(name))

    async def exercise():
        initial = await application.whisper_model_status(device="cpu")
        assert initial["models"][1]["state"] == "missing"
        started = await application.whisper_model_download("base", device="cpu")
        assert started["state"] == "downloading"
        for _ in range(30):
            await asyncio.sleep(0.01)
            result = await application.whisper_model_status(device="cpu")
            if result["models"][1]["state"] == "installed":
                break
        assert result["models"][1]["state"] == "installed"

    asyncio.run(exercise())
