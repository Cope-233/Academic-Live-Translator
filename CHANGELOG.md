# Changelog

## Unreleased

- Windows first installation now downloads only the configured local Whisper model (`base` by default) instead of all five sizes.
- Whisper models are installed on demand from the WebUI with installation status, background downloads, retry attempts, and Hugging Face cache reuse.
- Model files are validated before being considered installed. Failed model downloads do not change the saved ASR selection.
- Portable CUDA archive downloads now resume through HTTP Range and retry broken/incomplete archives. The installation marker was updated to allow lightweight migration.

## 1.0 — 2026-10-13

First stable release, focused on making Defense Q&A usable as a persistent live viva workflow rather than a one-shot Codex handoff.

- Split Defense prompting into a manually editable **system prompt** and a WebUI-editable **user prompt**. The system prompt is stored in `data/defense_config.json`; each request combines system prompt, user prompt, current committee question, and recent follow-up context.
- Replaced the free-text Codex model field with a **model dropdown** populated automatically from the current Codex CLI model catalog (`codex debug models`, with local catalog-cache fallback).
- Replaced the three Fast/Balanced/Deep presets with a **Reasoning effort** dropdown that follows the reasoning levels advertised by the selected Codex model, including newer levels such as `xhigh`, `max`, and `ultra` when available.
- Added persistent **Defense Q&A history** to each ALT Session. Stored turns include original question, translation, answer, model, reasoning effort, latency, and timestamp.
- Added **follow-up context**: recent Q&A turns from the current Session are automatically included when the next question is sent to Codex.
- Added a **History** action in the live Defense bar and a persistent Q&A history panel in the answer drawer.
- Session search now includes Defense questions and answers. Markdown, TXT, and JSON exports include saved Defense Q&A history.
- Existing beta 0.9 Defense settings migrate automatically: Fast → `low`, Balanced → `medium`, Deep → `high`.
- Promoted application, startup labels, tests, and documentation to stable version **1.0**.

## beta 0.9 — 2026-10-13

Defense Q&A beta focused on a lightweight Codex CLI handoff instead of adding a local RAG stack or large QA model to ALT.

- Added **Defense Q&A · Experimental** to the Live workspace without changing the existing ASR or translation pipeline.
- Transcript and translation segments can be selected directly; `Shift + click` selects a continuous multi-segment committee question.
- Added a compact Defense action bar and answer drawer with copy support, while keeping the existing bilingual workspace layout unchanged when Defense mode is off.
- Added a dedicated Codex CLI backend using `codex exec` in read-only mode with approval prompts disabled for unattended live Q&A.
- Added three response presets: **Fast** (`low` reasoning, default), **Balanced** (`medium`), and **Deep** (`high`).
- Model selection defaults to **Auto**, allowing Codex to use the current account/default model; advanced users may provide an explicit model ID.
- Added automatic Codex CLI installation/login status detection and a one-click action to open the portable `data/defense/` workspace.
- Defense reference files remain outside the ALT session database. Users place searchable Markdown/TXT thesis materials in `data/defense/`; Codex reads them only when a question is submitted.
- Added bilingual Defense Q&A UI, backend tests, JavaScript syntax validation, and beta 0.9 startup/release metadata.
- No embedding model, vector database, reranker, or local large language model is required for Defense Q&A.

## beta 0.8 — 2026-10-07

Customization and realtime-output beta focused on lower perceived latency and user-controlled live behavior.

- Renamed **Academic & Capture** to **Custom Settings** and reorganized it into language/translation, speech segmentation, realtime, and capture/storage sections.
- Exposed additional persistent settings including speech threshold, pre-roll, translation context segments, academic-term preservation, screenshot monitor, realtime startup delay, ASR partial interval, and translation partial interval.
- All custom values are saved to the portable `data/config.json` and restored automatically on the next launch; existing beta 0.7 configs migrate through the normal model defaults without losing provider profiles.
- Added an **Output mode** selector to the Live workspace with **Sentence mode** as the default and **Realtime · Experimental** as the optional low-latency mode.
- Realtime mode performs incremental provisional ASR while speech is still in progress, then performs throttled provisional translation updates.
- Added latest-snapshot scheduling for realtime ASR so stale partial jobs are dropped instead of building an inference queue.
- Provisional realtime text is rendered in-place in the WebUI and floating window, visually distinguished from finalized text, and is never written to session history or exports.
- Endpoint completion still triggers one final ASR pass and one final translation pass; only those final results are persisted.
- Retained the existing sentence-mode pipeline unchanged for users who prefer maximum stability and lower compute/network usage.
- Updated WebUI, startup labels, tests, example configuration, and release metadata to beta 0.8.

## beta 0.7 — 2026-10-07

Persistent provider-profile beta focused on reliable local/remote configuration switching.

- Added independent ASR profiles for Local Whisper and OpenAI-compatible services such as llama.cpp, vLLM, LM Studio, and LocalAI.
- Added independent translation profiles for Bing Free, Microsoft Translator, and OpenAI-compatible services.
- The WebUI now restores the last saved active ASR and translation providers during startup instead of showing the HTML fallback choices first.
- Switching providers now stores the previous provider's form state and loads the selected provider's own settings without clearing inactive URLs, API keys, endpoints, models, device choices, or regions.
- Removed the beta 0.4–0.6 behavior that erased OpenAI-compatible / llama.cpp fields when Local Whisper or Bing was saved.
- Existing beta 0.6 `data/config.json` files are migrated automatically: the currently configured providers are placed into provider-specific profiles while runtime-compatible `asr` / `translation` mirrors are preserved.
- Added provider-profile migration and persistence tests, including stale legacy-mirror recovery and inactive-profile retention.
- Fixed the beta 0.6 floating-window wrapper name collision and updated the WebUI/floating-window version label to beta 0.7.

## beta 0.6 — 2026-10-04

Apple silicon and cross-platform installation beta.

- Added MLX Whisper inference through Apple MLX / Metal on M-series Macs.
- Added automatic, CPU, and Apple silicon GPU device modes on supported Macs; Windows retains automatic, CPU, and CUDA modes.
- Automatic mode selects MLX on Apple silicon, CUDA when the Windows NVIDIA runtime is available, and CPU as the fallback.
- Installers detect the platform and architecture, install the matching dependencies, prepare the selected model, and run real inference checks before marking setup complete.
- Added project-local MLX model storage on macOS; other model sizes download on first selection to avoid preloading every model.
- Preserved beta 0.5 portable CUDA setup, model installation, and capture reliability fixes.
- Updated Chinese and English installation guides, startup scripts, app version, and release metadata.

## beta 0.5 — 2026-10-04

Whisper/Bing live-path and Windows microphone/configuration reliability beta.

- Prevented settings and live-capture actions from using the WebUI before its configuration has finished loading; concurrent early actions now share the same initialization request.
- Native Windows capture now confirms the WASAPI device opened instead of waiting for the first audio frame, so a quiet input no longer produces a false startup failure; device-open errors are reported immediately.
- Fixed Windows CUDA runtime extraction: the bundled 7z archive uses BCJ2, which `py7zr` does not support, so Windows now extracts it with the built-in `tar.exe`.
- The installer now checks dependency and asset-install exit codes, verifies its completion marker, and stops instead of launching after a failed setup.
- CUDA installation is not marked complete unless the real Whisper CUDA inference self-test succeeds.
- The app registers the project-local CUDA DLL directory itself, so manually launched WebUI processes can use the portable runtime too.
- Bumped the WebUI, API, and install marker to beta 0.5.

## beta 0.4 — 2026-10-04

Local Whisper / Bing reliability and one-click portable installation beta.

- Decoupled live ASR from translation: a recognized source segment is now saved and displayed immediately, then updated in place when translation finishes.
- Translation failures no longer hide or discard successfully recognized Whisper text.
- Added stage-specific live error logging for ASR and translation failures.
- Fixed Bing Free response handling by extracting `translations[0].text` instead of stringifying the complete response object.
- Added Bing-specific language mapping, including `auto-detect`, `zh-Hans`, and `zh-Hant`.
- Local Whisper provider tests now execute a real inference pass instead of checking model construction only, exposing missing CUDA runtime libraries such as `cublas64_12.dll` before a live session.
- Local Whisper can load directly from project-local model folders under `models/faster-whisper/<model>/`.
- Added a Windows one-click installer: `install.bat` / `install.ps1` creates `.venv`, installs dependencies, and prepares all five supported Whisper models (`tiny`, `base`, `small`, `medium`, `large-v3-turbo`).
- On Windows systems with an NVIDIA GPU, the installer also prepares a project-local CUDA 12 cuBLAS/cuDNN runtime under `runtime/cuda12/bin` without changing the system-wide CUDA installation.
- Added real CPU and CUDA Whisper inference self-tests during installation; CUDA failure leaves CPU mode available and reports the failure explicitly.
- Added `start_webui.bat`; the first launch automatically invokes the one-click installer when beta 0.4 assets are not yet prepared.
- Local Whisper and Bing modes now clear stale OpenAI-compatible/llama.cpp fields when settings are saved.
- Portable runtime downloads are excluded from Git through `runtime/`.

## beta 0.3 — 2026-10-04

Windows native-microphone reliability beta.

- Fixed Windows native microphone capture for external / USB microphones that are detected correctly but fail to deliver audio.
- Native microphone enumeration is now restricted to WASAPI endpoints, removing duplicate MME / DirectSound-style entries.
- The native capture backend now negotiates a compatible PCM16 sample-rate/channel combination instead of assuming `defaultSampleRate + maxInputChannels` will open successfully.
- Microphone capture prefers mono for speech recognition while WASAPI loopback continues to prefer stereo.
- The WebUI now waits for a real native audio-level packet before marking Windows microphone startup as successful.
- Added actionable timeout / connection messages when a native microphone opens but no audio stream arrives.
- Added beta 0.3 unit coverage for native capture format preference.
- Retains the beta 0.2 experimental Document Picture-in-Picture floating window.

## beta 0.2 — 2026-10-04

Floating-window beta focused on single-screen academic use.

- Added an **Experimental Floating Window** based on Document Picture-in-Picture for supported desktop Chromium browsers.
- Floating window can remain above Zoom, WebEx, browser classes, slide decks, and other desktop applications.
- Two-column layout keeps original text and translation aligned by segment with one shared scrollbar.
- Floating subtitles auto-follow the newest segment and pause follow mode when the user scrolls upward.
- Added `Back to WebUI` and close controls inside the floating window.
- Added configurable floating-window default width, height, and subtitle font size.
- Manual floating-window resizing automatically persists the new width and height to the portable config.
- Standard WebUI remains unchanged as the main capture, ASR, translation, notes, and session-management workspace.
- Updated Chinese / English documentation for browser support and usage limitations.

## beta 0.1 — 2026-10-04

First public beta.

- Portable-by-default storage: `data/`, `models/`, `cache/`, `logs/`, `.venv/` stay inside the project directory.
- Removed automatic AppData / legacy v0.2 data reuse.
- Local Faster-Whisper models download into `models/faster-whisper/`.
- Hugging Face, pip, and temporary caches are redirected into `cache/`.
- WebUI-only distribution.
- Unified Live workspace for lectures, meetings, interviews, seminars, and conferences.
- Library session deletion.
- Chinese / English interface switching.
- Unified OpenAI Chat Completions mode for remote ASR.
- Mainstream target-language list; Malay remains available as a source language.
- Synchronized scrolling between original and translation panels.
- Automatic follow-to-latest behavior with manual-scroll pause/resume.
- Compact interface-language settings UI.
- GitHub-friendly default providers: Local Faster-Whisper + Bing Free (experimental).
- OpenAI-compatible provider remains the generic integration path for llama.cpp, vLLM, LM Studio, LocalAI, and compatible services.
- Lower endpointing latency and HTTP connection reuse.

Stable releases use semantic version numbers beginning with 1.0.
