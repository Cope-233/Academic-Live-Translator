# Academic Live Translator

[简体中文](./README.md) | **English**

Academic Live Translator is a local-first WebUI for real-time speech transcription, translation, and academic session capture. It is designed for lectures, seminars, conferences, meetings, interviews, and recorded media.

## Project overview

The project combines live audio capture, ASR, translation, and academic note-taking in one browser workspace. Models, configuration, caches, and session data are kept inside the project directory whenever possible, making the application easy to move and manage.

Main features:

- Real-time side-by-side original text and translation with synchronized scrolling and follow-to-latest behavior
- Sentence output and experimental realtime incremental output; realtime mode updates provisional transcription and translation during speech, then stores only the finalized result in the Session
- Local Whisper ASR: `tiny`, `base`, `small`, `medium`, and `large-v3-turbo`
- MLX / Metal acceleration on Apple silicon, CUDA support on Windows NVIDIA systems, and CPU fallback elsewhere
- Bing Free, Microsoft Translator, and OpenAI-compatible translation providers
- OpenAI-compatible ASR for services such as llama.cpp, vLLM, LM Studio, and LocalAI
- Browser microphone, tab / screen audio, and system-audio + microphone mixing
- Windows WASAPI loopback and native microphone capture
- Audio and video file transcription and translation
- Experimental bilingual floating subtitle window for Zoom, WebEx, browser classes, or presentations
- Custom speech segmentation, realtime update intervals, translation context, terminology preservation, and capture/storage settings with persistent local configuration
- Academic glossary, markers, notes, screenshots, and searchable Session Library
- TXT, Markdown, SRT, and JSON export
- Portable-by-default storage: `.venv/`, `data/`, `models/`, `runtime/`, `cache/`, and `logs/` stay inside the project directory

### Choosing a Whisper model

The default model is `base`. If you are unsure which model to use, keep the default. For live subtitles, a larger model is not always better: on slower hardware it may fall behind the speaker and delay the translation pipeline.

| Model | Parameters | Official reference VRAM | Recommended hardware | Best for |
| --- | ---: | ---: | --- | --- |
| `tiny` | 39M | ~1 GB | 4-core CPU and 8 GB system RAM; discrete GPU not required | Low-end systems where latency matters more than accuracy |
| `base` | 74M | ~1 GB | Modern 4-core+ CPU and 8 GB system RAM; GPU improves speed | **Default recommendation** with the best overall balance |
| `small` | 244M | ~2 GB | Recommended: 6-core CPU and 16 GB RAM, or NVIDIA GPU with 4 GB+ VRAM | Mid-range systems that need better recognition accuracy |
| `medium` | 769M | ~5 GB | Recommended: NVIDIA GPU with 6 GB+ VRAM, or Apple silicon with 16 GB+ unified memory; ordinary CPU-only use is not recommended for live transcription | Higher-end systems where accuracy is prioritized |
| `large-v3-turbo` | 809M | ~6 GB | Recommended: NVIDIA GPU with 8 GB+ VRAM, or Apple silicon with 16 GB+ unified memory; CPU-only is not recommended for live subtitles | High-performance systems using the largest supported model while retaining good speed |

> VRAM figures are approximate values published by OpenAI for Whisper. Academic Live Translator uses faster-whisper on Windows / Linux and can use MLX on Apple silicon, so actual memory usage and speed depend on the device, compute type, and audio. CPU-only users should generally choose `tiny`, `base`, or `small`.

## Usage

### Windows

Install Python first. After downloading or cloning the repository, simply double-click:

```text
start_webui.bat
```

On first launch, the application initializes the local environment automatically: it creates `.venv/`, installs dependencies, prepares local Whisper models, and, when an NVIDIA GPU is detected, prepares a project-local CUDA runtime.

The WebUI opens at:

```text
http://127.0.0.1:8765
```

For later launches, run the same file again:

```text
start_webui.bat
```

PowerShell is also supported:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start_webui.ps1
```

Windows users can select WASAPI system audio as the input source to capture audio directly from Zoom, WebEx, browser courses, or other desktop applications.

### macOS (Apple silicon)

For M-series Macs, native arm64 Python is recommended.

From the project directory, run:

```bash
chmod +x start_webui.sh
./start_webui.sh
```

The first launch creates `.venv/`, installs dependencies, and prepares the selected Whisper model. Auto mode prefers MLX / Metal acceleration on Apple silicon; CPU mode remains available under **Settings → ASR Provider → Device**.

The WebUI is available at:

```text
http://127.0.0.1:8765
```

If the launcher reports that Python is not running as `arm64`, install a native Apple silicon Python, remove the project `.venv/`, and run the launcher again.

### Linux / Intel Mac

From the project directory, run:

```bash
chmod +x start_webui.sh
./start_webui.sh
```

Linux and Intel Macs use CPU Whisper by default and support browser microphone capture, tab / screen audio, and media-file workflows.

The WebUI is available at:

```text
http://127.0.0.1:8765
```

### After startup

1. Open the **Live** workspace and choose an audio source.
2. Select source and target languages, then choose **Sentence mode** or the experimental **Realtime** mode. Sentence mode is the default.
3. Click **Start listening**.
4. Original text and translation appear in the current Session. Realtime provisional results are display-only and are replaced by the finalized result when the speech segment ends.
5. To use another ASR or translation service, configure Local Whisper, Microsoft Translator, or an OpenAI-compatible provider under **Settings**.
6. Fine-tune speech detection, segmentation, realtime updates, translation, and capture/storage behavior under **Settings → Custom settings**. Saved values are restored on the next launch.
7. For single-screen Zoom, WebEx, or browser-course use, enable the **Experimental** floating window to keep original text and translation above other windows.

Sessions, models, caches, recordings, and screenshots are stored inside the project directory by default, so the whole installation can be moved or removed as one folder.