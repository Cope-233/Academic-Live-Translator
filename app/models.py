from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

ProviderMode = Literal["local_whisper","openai_chat","bing_web","azure_translator"]
AsrProviderMode = Literal["local_whisper","openai_chat"]
TranslationProviderMode = Literal["bing_web","azure_translator","openai_chat"]
SessionMode = Literal["live","media","lecture","meeting"]
InputSource = Literal["microphone","browser_system","browser_mix","native_system","native_microphone","media_file"]
MarkerKind = Literal["important","question","idea","reference","follow_up","note"]
OutputMode = Literal["sentence","realtime"]

class ProviderConfig(BaseModel):
    name: str = "Local Whisper"
    mode: ProviderMode = "local_whisper"
    base_url: str = ""
    api_key: str = ""
    model: str = "base"
    endpoint: str | None = None
    timeout_seconds: float = 120.0
    temperature: float = 0.0
    max_tokens: int = 4096
    device: Literal["auto","cpu","cuda","apple"] = "auto"
    compute_type: str = "auto"
    region: str = ""


def _default_asr_profiles() -> dict[str, ProviderConfig]:
    return {
        "local_whisper": ProviderConfig(
            name="Local Whisper",
            mode="local_whisper",
            model="base",
            device="auto",
            compute_type="auto",
        ),
        "openai_chat": ProviderConfig(
            name="OpenAI-compatible ASR",
            mode="openai_chat",
            base_url="http://127.0.0.1:8080/v1",
            model="",
        ),
    }


def _default_translation_profiles() -> dict[str, ProviderConfig]:
    return {
        "bing_web": ProviderConfig(
            name="Bing Translate (Free)",
            mode="bing_web",
            model="bing",
            temperature=0.0,
        ),
        "azure_translator": ProviderConfig(
            name="Microsoft Translator",
            mode="azure_translator",
            base_url="https://api.cognitive.microsofttranslator.com",
            model="translator-v3",
            temperature=0.0,
        ),
        "openai_chat": ProviderConfig(
            name="OpenAI-compatible Translation",
            mode="openai_chat",
            model="",
            temperature=0.0,
        ),
    }


class ProviderProfiles(BaseModel):
    """Persistent provider-specific settings plus the currently active providers."""

    active_asr: AsrProviderMode = "local_whisper"
    active_translation: TranslationProviderMode = "bing_web"
    asr: dict[str, ProviderConfig] = Field(default_factory=_default_asr_profiles)
    translation: dict[str, ProviderConfig] = Field(default_factory=_default_translation_profiles)

class LiveConfig(BaseModel):
    sample_rate: int = 16000
    output_mode: OutputMode = "sentence"
    speech_threshold: float = Field(default=0.010, ge=0.001, le=0.5)
    silence_ms: int = Field(default=420, ge=150, le=5000)
    min_speech_ms: int = Field(default=280, ge=100, le=5000)
    max_segment_ms: int = Field(default=12000, ge=3000, le=120000)
    pre_roll_ms: int = Field(default=220, ge=0, le=2000)
    realtime_min_audio_ms: int = Field(default=900, ge=400, le=5000)
    partial_interval_ms: int = Field(default=1000, ge=500, le=5000)
    partial_translation_interval_ms: int = Field(default=1800, ge=800, le=10000)

class CaptureConfig(BaseModel):
    input_source: InputSource = "microphone"
    native_output_device: int | None = None
    native_input_device: int | None = None
    save_audio: bool = True
    audio_format: Literal["flac","wav"] = "flac"
    screenshot_monitor: int = 1
    system_gain: float = Field(default=1.0, ge=0.0, le=2.0)
    microphone_gain: float = Field(default=0.85, ge=0.0, le=2.0)

class InterfaceConfig(BaseModel):
    language: Literal["zh-CN","en"] = "zh-CN"
    floating_window_width: int = Field(default=960, ge=420, le=2400)
    floating_window_height: int = Field(default=420, ge=220, le=1400)
    floating_window_font_size: int = Field(default=18, ge=12, le=36)

class AcademicConfig(BaseModel):
    source_language: str = "auto"
    target_language: str = "Chinese"
    glossary: str = ""
    glossary_profiles: dict[str,str] = Field(default_factory=lambda:{
        "General":"",
        "Tourism & Hospitality":"Hospitality and Tourism = 酒店与旅游\nOnline Travel Agency = 在线旅行社\nDestination Image = 目的地形象\nSmart Tourism = 智慧旅游",
        "AI & LLM":"Large Language Model = 大语言模型\nGenerative Artificial Intelligence = 生成式人工智能\nArtificial Intelligence Generated Content = 人工智能生成内容",
        "SEM":"Structural Equation Modeling = 结构方程模型\nPartial Least Squares Structural Equation Modeling = 偏最小二乘结构方程模型\nMeasurement Invariance = 测量不变性"})
    active_glossary_profile: str = "General"
    translation_mode: Literal["low_latency","balanced","context"] = "low_latency"
    context_segments: int = Field(default=1, ge=0, le=5)
    preserve_academic_terms: bool = True
    translation_prompt: str = "Translate the CURRENT text into {target_language}. Preserve academic terminology, proper nouns, abbreviations, numbers, and citations. Use the context only to resolve references and terminology. Output only the translation of CURRENT.\n\n{glossary_block}{context_block}CURRENT:\n{text}"

class AppConfig(BaseModel):
    interface: InterfaceConfig = InterfaceConfig()
    # Active-provider mirrors retained for runtime/backward compatibility.
    asr: ProviderConfig = ProviderConfig(name="Local Whisper",mode="local_whisper",model="base",device="auto",compute_type="auto")
    translation: ProviderConfig = ProviderConfig(name="Bing Translate (Free)",mode="bing_web",model="bing",temperature=0.0)
    providers: ProviderProfiles = Field(default_factory=ProviderProfiles)
    live: LiveConfig = LiveConfig()
    capture: CaptureConfig = CaptureConfig()
    academic: AcademicConfig = AcademicConfig()

class TranslateRequest(BaseModel):
    text: str
    target_language: str | None = None
class SessionCreateRequest(BaseModel):
    title: str | None = None
    mode: SessionMode = "live"
    input_source: InputSource | None = None
class SessionPatchRequest(BaseModel):
    title: str | None = None
class BookmarkRequest(BaseModel):
    bookmarked: bool = True
class AnnotationRequest(BaseModel):
    kind: MarkerKind = "note"
    text: str = ""
    timestamp_ms: int | None = None
    segment_id: str | None = None
class ScreenshotRequest(BaseModel):
    timestamp_ms: int | None = None
    monitor: int | None = None
    note: str = ""
class Segment(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    source: str
    translation: str = ""
    language: str | None = None
    bookmarked: bool = False
class Annotation(BaseModel):
    id: str
    timestamp_ms: int
    kind: MarkerKind
    text: str = ""
    segment_id: str | None = None
    created_at: str
class ScreenshotAsset(BaseModel):
    id: str
    timestamp_ms: int
    filename: str
    note: str = ""
    created_at: str
class DefenseQATurn(BaseModel):
    id: str
    original: str = ""
    translation: str = ""
    answer: str
    model: str = "auto"
    reasoning_effort: str = "medium"
    duration_ms: int = 0
    created_at: str
class SessionData(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    mode: SessionMode = "live"
    input_source: InputSource = "microphone"
    source_language: str = "auto"
    target_language: str = "Chinese"
    segments: list[Segment] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    screenshots: list[ScreenshotAsset] = Field(default_factory=list)
    audio_files: list[str] = Field(default_factory=list)
    defense_qa: list[DefenseQATurn] = Field(default_factory=list)