import subprocess

import pytest

from app import install_assets
from app import __version__
from app.audio import SpeechEndpointDetector
from app.models import AppConfig
from app.config import CACHE_DIR, DATA_DIR, MODELS_DIR, PROJECT_ROOT, _migrate_config
from app.native_capture import NativeAudioCapture, NativeCaptureInfo, _capture_candidates
from app import providers
from app.models import ProviderConfig
from app.providers import _bing_lang, _parse_bing_result
from app import main


def test_version():
    assert __version__ == "beta 0.9"


def test_defaults():
    cfg = AppConfig()
    assert cfg.interface.language == "zh-CN"
    assert cfg.interface.floating_window_width == 960
    assert cfg.interface.floating_window_height == 420
    assert cfg.interface.floating_window_font_size == 18
    assert cfg.asr.mode == "local_whisper"
    assert cfg.asr.model == "base"
    assert cfg.translation.mode == "bing_web"
    assert cfg.providers.active_asr == "local_whisper"
    assert cfg.providers.active_translation == "bing_web"
    assert cfg.providers.asr["openai_chat"].mode == "openai_chat"
    assert cfg.providers.translation["azure_translator"].mode == "azure_translator"
    assert cfg.academic.target_language == "Chinese"
    assert cfg.live.output_mode == "sentence"
    assert cfg.live.speech_threshold == 0.010
    assert cfg.live.silence_ms == 420
    assert cfg.live.pre_roll_ms == 220
    assert cfg.live.realtime_min_audio_ms == 900
    assert cfg.live.partial_interval_ms == 1000
    assert cfg.live.partial_translation_interval_ms == 1800


def test_realtime_output_mode_and_custom_settings_validate():
    cfg = AppConfig(live={
        "output_mode": "realtime",
        "speech_threshold": 0.02,
        "silence_ms": 300,
        "min_speech_ms": 200,
        "max_segment_ms": 8000,
        "pre_roll_ms": 180,
        "realtime_min_audio_ms": 700,
        "partial_interval_ms": 800,
        "partial_translation_interval_ms": 1500,
    }, academic={"context_segments": 3, "preserve_academic_terms": False})
    assert cfg.live.output_mode == "realtime"
    assert cfg.live.speech_threshold == 0.02
    assert cfg.live.partial_interval_ms == 800
    assert cfg.academic.context_segments == 3
    assert cfg.academic.preserve_academic_terms is False


def test_speech_detector_snapshot_does_not_finalize_segment():
    cfg = AppConfig(live={"speech_threshold": 0.001, "min_speech_ms": 100, "pre_roll_ms": 0}).live
    detector = SpeechEndpointDetector(cfg)
    pcm = (1000).to_bytes(2, byteorder="little", signed=True) * 3200  # 200 ms at 16 kHz
    level, result = detector.feed(pcm)
    assert level > cfg.speech_threshold
    assert result is None
    snapshot = detector.snapshot()
    assert snapshot is not None
    assert snapshot.duration_ms == 200
    assert detector.in_speech is True


def test_apple_silicon_auto_uses_mlx_and_cpu_stays_cpu(monkeypatch):
    monkeypatch.setattr(providers.sys, "platform", "darwin")
    monkeypatch.setattr(providers.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(providers, "_mlx_whisper_available", lambda: True)

    assert providers._whisper_device(ProviderConfig(device="auto")) == ("apple", "float16")
    assert providers._whisper_device(ProviderConfig(device="cpu")) == ("cpu", "int8")
    assert providers._whisper_device(ProviderConfig(device="apple")) == ("apple", "float16")
    assert providers.supported_whisper_devices() == ["auto", "cpu", "apple"]


def test_legacy_cuda_config_maps_to_apple_on_m_series_mac(monkeypatch):
    monkeypatch.setattr(providers.sys, "platform", "darwin")
    monkeypatch.setattr(providers.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(providers, "_mlx_whisper_available", lambda: True)

    assert providers._whisper_device(ProviderConfig(device="cuda")) == ("apple", "float16")


def test_apple_device_config_maps_to_cpu_off_apple_silicon(monkeypatch):
    monkeypatch.setattr(providers.sys, "platform", "darwin")
    monkeypatch.setattr(providers.platform, "machine", lambda: "x86_64")

    assert providers._whisper_device(ProviderConfig(device="apple")) == ("cpu", "int8")


def test_mlx_whisper_model_repositories_are_mapped():
    assert providers.MLX_WHISPER_REPOS["base"] == "mlx-community/whisper-base-mlx"
    assert providers.MLX_WHISPER_REPOS["large-v3-turbo"] == "mlx-community/whisper-large-v3-turbo"


def test_audio_source_options_follow_platform(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "darwin")
    assert main.supported_audio_sources() == ["microphone", "browser_system", "browser_mix"]

    monkeypatch.setattr(main.sys, "platform", "win32")
    assert main.supported_audio_sources() == [
        "microphone", "browser_system", "browser_mix", "native_system", "native_microphone"
    ]


def test_floating_window_bounds():
    cfg = AppConfig(interface={"language":"zh-CN","floating_window_width":420,"floating_window_height":220,"floating_window_font_size":12})
    assert cfg.interface.floating_window_width == 420
    assert cfg.interface.floating_window_height == 220
    assert cfg.interface.floating_window_font_size == 12


def test_portable_paths():
    assert DATA_DIR == PROJECT_ROOT / "data"
    assert MODELS_DIR == PROJECT_ROOT / "models"
    assert CACHE_DIR == PROJECT_ROOT / "cache"


def test_native_microphone_prefers_mono_wasapi_format():
    device = {"defaultSampleRate": 48000, "maxInputChannels": 2}
    assert _capture_candidates(device, False)[0] == (48000, 1)


def test_native_loopback_prefers_stereo_wasapi_format():
    device = {"defaultSampleRate": 48000, "maxInputChannels": 2}
    assert _capture_candidates(device, True)[0] == (48000, 2)


def test_native_capture_waits_for_device_open():
    capture = NativeAudioCapture(17, True, None, None)
    capture.info = NativeCaptureInfo(17, "Loopback", 48000, 2)
    capture._ready_event.set()
    assert capture.wait_until_ready(timeout=0.01) is capture.info


def test_native_capture_reports_device_open_error():
    capture = NativeAudioCapture(17, True, None, None)
    capture.error = "device busy"
    capture._ready_event.set()
    with pytest.raises(RuntimeError, match="device busy"):
        capture.wait_until_ready(timeout=0.01)


def test_bing_language_mapping():
    assert _bing_lang("auto", source=True) == "auto-detect"
    assert _bing_lang("Chinese") == "zh-Hans"
    assert _bing_lang("zh-tw") == "zh-Hant"


def test_bing_response_parser():
    payload = {"translations": [{"text": "你好，这是一个测试。", "to": "zh-Hans"}]}
    assert _parse_bing_result(payload) == "你好，这是一个测试。"


def test_cuda_archive_uses_windows_tar(monkeypatch, tmp_path):
    windows_dir = tmp_path / "Windows"
    tar = windows_dir / "System32" / "tar.exe"
    tar.parent.mkdir(parents=True)
    tar.touch()
    monkeypatch.setattr(install_assets.sys, "platform", "win32")
    monkeypatch.setenv("WINDIR", str(windows_dir))
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(install_assets.subprocess, "run", fake_run)
    archive = tmp_path / "runtime.7z"
    destination = tmp_path / "extracted"
    install_assets._extract_cuda_archive(archive, destination)

    assert calls[0][0] == [str(tar), "-xf", str(archive), "-C", str(destination)]


def test_cuda_archive_extraction_failure_is_reported(monkeypatch, tmp_path):
    windows_dir = tmp_path / "Windows"
    tar = windows_dir / "System32" / "tar.exe"
    tar.parent.mkdir(parents=True)
    tar.touch()
    monkeypatch.setattr(install_assets.sys, "platform", "win32")
    monkeypatch.setenv("WINDIR", str(windows_dir))
    monkeypatch.setattr(
        install_assets.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 2, "", "archive error"),
    )

    with pytest.raises(RuntimeError, match="archive error"):
        install_assets._extract_cuda_archive(tmp_path / "runtime.7z", tmp_path / "extracted")


def test_legacy_asr_migration():
    raw = {
        "asr": {"mode": "openai_transcriptions", "endpoint": "http://127.0.0.1:8080/v1/audio/transcriptions"},
        "academic": {"target_language": "Malay"},
    }
    migrated = _migrate_config(raw)
    assert migrated["asr"]["mode"] == "openai_chat"
    assert migrated["asr"]["endpoint"] is None
    assert migrated["providers"]["active_asr"] == "openai_chat"
    assert migrated["academic"]["target_language"] == "Chinese"
    assert migrated["interface"]["language"] == "zh-CN"


def test_beta06_remote_config_is_migrated_into_its_profile():
    raw = {
        "asr": {
            "name": "llama.cpp ASR",
            "mode": "openai_chat",
            "base_url": "http://127.0.0.1:8080/v1",
            "api_key": "local-key",
            "model": "Qwen3-ASR-1.7B",
            "endpoint": "/chat/completions",
        },
        "translation": {
            "name": "Bing Translate (Free)",
            "mode": "bing_web",
            "model": "bing",
        },
    }
    migrated = _migrate_config(raw)
    profile = migrated["providers"]["asr"]["openai_chat"]

    assert migrated["providers"]["active_asr"] == "openai_chat"
    assert profile["base_url"] == "http://127.0.0.1:8080/v1"
    assert profile["api_key"] == "local-key"
    assert profile["model"] == "Qwen3-ASR-1.7B"
    assert migrated["asr"] == profile


def test_inactive_provider_profiles_survive_active_provider_changes():
    raw = AppConfig().model_dump()
    raw["providers"]["active_asr"] = "local_whisper"
    raw["providers"]["asr"]["openai_chat"].update({
        "name": "llama.cpp ASR",
        "base_url": "http://127.0.0.1:8080/v1",
        "api_key": "keep-me",
        "model": "Qwen3-ASR-1.7B",
        "endpoint": "/chat/completions",
    })
    raw["providers"]["active_translation"] = "bing_web"
    raw["providers"]["translation"]["openai_chat"].update({
        "name": "Local LLM Translation",
        "base_url": "http://127.0.0.1:8080/v1",
        "api_key": "translate-key",
        "model": "Qwen3-4B",
    })
    migrated = _migrate_config(raw)

    assert migrated["asr"]["mode"] == "local_whisper"
    assert migrated["translation"]["mode"] == "bing_web"
    assert migrated["providers"]["asr"]["openai_chat"]["api_key"] == "keep-me"
    assert migrated["providers"]["asr"]["openai_chat"]["model"] == "Qwen3-ASR-1.7B"
    assert migrated["providers"]["translation"]["openai_chat"]["api_key"] == "translate-key"
    assert migrated["providers"]["translation"]["openai_chat"]["model"] == "Qwen3-4B"


def test_active_profile_is_restored_even_if_legacy_mirror_is_stale():
    raw = AppConfig().model_dump()
    raw["providers"]["active_asr"] = "openai_chat"
    raw["providers"]["asr"]["openai_chat"].update({
        "name": "llama.cpp ASR",
        "base_url": "http://127.0.0.1:8080/v1",
        "model": "Qwen3-ASR-1.7B",
    })
    raw["asr"] = AppConfig().asr.model_dump()

    migrated = _migrate_config(raw)

    assert migrated["providers"]["active_asr"] == "openai_chat"
    assert migrated["asr"]["mode"] == "openai_chat"
    assert migrated["asr"]["name"] == "llama.cpp ASR"
    assert migrated["asr"]["model"] == "Qwen3-ASR-1.7B"
