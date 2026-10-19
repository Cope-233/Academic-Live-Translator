from __future__ import annotations

import asyncio
import json
import logging
import platform
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .audio import SpeechEndpointDetector, ensure_wav_16k_mono, segment_wav_bytes
from .capture_assets import capture_screen_png
from .config import DATA_DIR, load_config, save_config, session_assets_dir
from .exporters import export_json, export_markdown, export_srt, export_txt
from .model_downloads import backend_for, ensure_whisper_model, is_model_installed, validate_model
from .install_assets import WHISPER_MODELS
from .models import Annotation, AnnotationRequest, AppConfig, BookmarkRequest, ScreenshotAsset, ScreenshotRequest, Segment, SessionCreateRequest, SessionPatchRequest, TranslateRequest
from .native_capture import NativeAudioCapture, list_native_devices
from .providers import academic_hotwords, close_http_client, prepare_local_whisper, supported_whisper_devices, test_provider, transcribe_wav, translate_text
from .recording import SessionAudioRecorder
from .store import add_annotation, add_audio_file, add_screenshot, append_segment, create_session, delete_session, get_session, list_sessions, now_iso, patch_title, set_bookmark, update_segment

logger = logging.getLogger("academic_live_translator")


def runtime_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]

ROOT = runtime_root()
STATIC_DIR = ROOT / "static"
app = FastAPI(title="Academic Live Translator", version=__version__)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def index(): return FileResponse(STATIC_DIR / "index.html")

@app.get("/presentation.html")
async def presentation_page(): return FileResponse(STATIC_DIR / "presentation.html")

@app.get("/api/health")
async def health(): return {"ok": True, "app": "Academic Live Translator", "version": __version__}

@app.get("/api/system/capabilities")
async def system_capabilities():
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "whisper_devices": supported_whisper_devices(),
        "audio_sources": supported_audio_sources(),
    }


def supported_audio_sources() -> list[str]:
    audio_sources = ["microphone", "browser_system", "browser_mix"]
    if sys.platform == "win32":
        audio_sources.extend(["native_system", "native_microphone"])
    return audio_sources

@app.get("/api/config")
async def get_config(): return load_config().model_dump()

@app.put("/api/config")
async def put_config(config: AppConfig):
    save_config(config); return {"ok": True}

# Download tasks outlive the HTTP request, so switching tabs does not discard work.
_WHISPER_DOWNLOAD_JOBS: dict[str, dict[str, str]] = {}


def _whisper_job_key(name: str, device: str) -> str:
    return f"{name}:{backend_for(device)}"


def _whisper_model_state(name: str, device: str) -> dict[str, str | bool]:
    job = _WHISPER_DOWNLOAD_JOBS.get(_whisper_job_key(name, device), {})
    if job.get("state") == "downloading":
        return {"name": name, "installed": False, "state": "downloading", "error": ""}
    installed = is_model_installed(name, device)
    return {
        "name": name,
        "installed": installed,
        "state": "installed" if installed else job.get("state", "missing"),
        "error": "" if installed else job.get("error", ""),
    }


@app.get("/api/models/whisper")
async def whisper_model_status(device: str = "auto"):
    try:
        backend_for(device)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"models": [_whisper_model_state(name, device) for name in WHISPER_MODELS]}


@app.post("/api/models/whisper/{model_name}/download")
async def whisper_model_download(model_name: str, device: str = "auto"):
    try:
        validate_model(model_name)
        key = _whisper_job_key(model_name, device)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    current = _whisper_model_state(model_name, device)
    if current["state"] in {"installed", "downloading"}:
        return current
    _WHISPER_DOWNLOAD_JOBS[key] = {"state": "downloading", "error": ""}

    async def run_download():
        try:
            await asyncio.to_thread(ensure_whisper_model, model_name, device)
            _WHISPER_DOWNLOAD_JOBS[key] = {"state": "installed", "error": ""}
        except Exception as exc:
            logger.exception("Whisper model download failed: %s", model_name)
            _WHISPER_DOWNLOAD_JOBS[key] = {"state": "error", "error": str(exc)}

    asyncio.create_task(run_download())
    return _whisper_model_state(model_name, device)


@app.get("/api/audio/devices")
async def audio_devices(): return await asyncio.to_thread(list_native_devices)

@app.post("/api/providers/test/{kind}")
async def provider_test(kind: str):
    cfg = load_config()
    if kind == "asr": return await test_provider(cfg.asr, cfg.academic)
    if kind == "translation": return await test_provider(cfg.translation, cfg.academic)
    raise HTTPException(400, "kind must be 'asr' or 'translation'")

@app.post("/api/sessions")
async def new_session(req: SessionCreateRequest):
    cfg=load_config(); source=req.input_source or cfg.capture.input_source
    return create_session(req.title,source_language=cfg.academic.source_language,target_language=cfg.academic.target_language,mode=req.mode,input_source=source).model_dump()

@app.get("/api/sessions")
async def sessions(q: str=""):
    return [{"id":s.id,"title":s.title,"created_at":s.created_at,"updated_at":s.updated_at,"mode":s.mode,"input_source":s.input_source,"segments":len(s.segments),"annotations":len(s.annotations),"screenshots":len(s.screenshots),"source_language":s.source_language,"target_language":s.target_language} for s in list_sessions(query=q)]

@app.get("/api/sessions/{session_id}")
async def session_detail(session_id: str):
    try: return get_session(session_id).model_dump()
    except FileNotFoundError: raise HTTPException(404,"Session not found")

@app.delete("/api/sessions/{session_id}")
async def remove_session(session_id: str):
    try:
        delete_session(session_id); return {"ok":True,"id":session_id}
    except FileNotFoundError: raise HTTPException(404,"Session not found")

@app.patch("/api/sessions/{session_id}")
async def patch_session(session_id: str, req: SessionPatchRequest):
    try:
        if req.title is not None: return patch_title(session_id,req.title).model_dump()
        return get_session(session_id).model_dump()
    except FileNotFoundError: raise HTTPException(404,"Session not found")

@app.put("/api/sessions/{session_id}/segments/{segment_id}/bookmark")
async def bookmark(session_id: str, segment_id: str, req: BookmarkRequest):
    try: return set_bookmark(session_id,segment_id,req.bookmarked).model_dump()
    except FileNotFoundError: raise HTTPException(404,"Session not found")
    except KeyError: raise HTTPException(404,"Segment not found")

@app.post("/api/sessions/{session_id}/annotations")
async def create_annotation(session_id: str, req: AnnotationRequest):
    try: s=get_session(session_id)
    except FileNotFoundError: raise HTTPException(404,"Session not found")
    timestamp=req.timestamp_ms if req.timestamp_ms is not None else (s.segments[-1].end_ms if s.segments else 0)
    a=Annotation(id=uuid.uuid4().hex[:10],timestamp_ms=max(0,timestamp),kind=req.kind,text=req.text.strip(),segment_id=req.segment_id,created_at=now_iso())
    return add_annotation(session_id,a).model_dump()

@app.post("/api/sessions/{session_id}/screenshot")
async def session_screenshot(session_id: str, req: ScreenshotRequest):
    try: s=get_session(session_id)
    except FileNotFoundError: raise HTTPException(404,"Session not found")
    cfg=load_config(); timestamp=req.timestamp_ms if req.timestamp_ms is not None else (s.segments[-1].end_ms if s.segments else 0)
    try: filename,_=await asyncio.to_thread(capture_screen_png,session_id,req.monitor or cfg.capture.screenshot_monitor)
    except Exception as exc: raise HTTPException(500,str(exc))
    shot=ScreenshotAsset(id=uuid.uuid4().hex[:10],timestamp_ms=max(0,timestamp),filename=filename,note=req.note.strip(),created_at=now_iso())
    return add_screenshot(session_id,shot).model_dump()

@app.get("/api/sessions/{session_id}/assets/{asset_path:path}")
async def session_asset(session_id: str, asset_path: str):
    base=session_assets_dir(session_id).resolve(); path=(base/asset_path).resolve()
    if base not in path.parents and path != base: raise HTTPException(400,"Invalid asset path")
    if not path.exists() or not path.is_file(): raise HTTPException(404,"Asset not found")
    return FileResponse(path)

@app.get("/api/sessions/{session_id}/export/{fmt}")
async def export_session(session_id: str, fmt: str):
    try: session=get_session(session_id)
    except FileNotFoundError: raise HTTPException(404,"Session not found")
    safe="".join(c if c.isalnum() or c in "-_" else "_" for c in session.title)[:80] or session.id
    if fmt=="txt": return PlainTextResponse(export_txt(session),headers={"Content-Disposition":f'attachment; filename="{safe}.txt"'})
    if fmt=="md": return PlainTextResponse(export_markdown(session),media_type="text/markdown; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{safe}.md"'})
    if fmt=="srt": return PlainTextResponse(export_srt(session,False),media_type="application/x-subrip; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{safe}.srt"'})
    if fmt=="srt-translation": return PlainTextResponse(export_srt(session,True),media_type="application/x-subrip; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{safe}.translation.srt"'})
    if fmt=="json": return PlainTextResponse(export_json(session),media_type="application/json; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{safe}.json"'})
    raise HTTPException(400,"Unsupported export format")

@app.post("/api/translate")
async def translate(req: TranslateRequest):
    cfg=load_config()
    try: return {"translation":await translate_text(req.text,cfg.translation,cfg.academic,req.target_language)}
    except Exception as exc: raise HTTPException(502,f"Translation provider error: {exc}")

def _translation_context(session_id: str, cfg: AppConfig) -> list[str]:
    if cfg.academic.translation_mode=="low_latency": return []
    s=get_session(session_id); n=cfg.academic.context_segments
    if cfg.academic.translation_mode=="context": n=max(2,n)
    return [seg.source for seg in s.segments[-n:]] if n else []

@app.post("/api/process-file")
async def process_file(file: UploadFile=File(...), title: str|None=None):
    cfg=load_config(); raw=await file.read()
    try:
        wav=await asyncio.to_thread(ensure_wav_16k_mono,raw,file.filename or "input.wav")
        chunks=await asyncio.to_thread(segment_wav_bytes,wav,cfg.live)
    except Exception as exc: raise HTTPException(400,str(exc))
    session=create_session(title or Path(file.filename or "Media transcription").stem,cfg.academic.source_language,cfg.academic.target_language,mode="media",input_source="media_file")
    try:
        for chunk in chunks:
            source,detected=await transcribe_wav(chunk.wav_bytes,cfg.asr,language=cfg.academic.source_language,prompt=academic_hotwords(cfg.academic))
            if not source: continue
            translation=await translate_text(source,cfg.translation,cfg.academic,context=_translation_context(session.id,cfg))
            session=append_segment(session.id,Segment(id=uuid.uuid4().hex[:10],start_ms=chunk.start_ms,end_ms=chunk.end_ms,source=source,translation=translation,language=detected))
    except Exception as exc: raise HTTPException(502,f"Model provider error: {exc}")
    return session.model_dump()

async def _process_live_segment(websocket: WebSocket, send_lock: asyncio.Lock, session_id: str, result, sequence: int, cfg: AppConfig|None=None):
    cfg=cfg or load_config()
    try:
        source,detected=await transcribe_wav(result.wav_bytes,cfg.asr,language=cfg.academic.source_language,prompt=academic_hotwords(cfg.academic))
    except Exception as exc:
        logger.exception("ASR failed for live segment %s", sequence)
        async with send_lock:
            try: await websocket.send_json({"type":"error","stage":"asr","sequence":sequence,"message":f"ASR: {exc}"})
            except Exception: pass
        return
    if not source:
        return

    translation_context=_translation_context(session_id,cfg)
    segment=Segment(id=uuid.uuid4().hex[:10],start_ms=result.start_ms,end_ms=result.end_ms,source=source,translation="",language=detected)
    append_segment(session_id,segment)
    async with send_lock:
        await websocket.send_json({"type":"segment","phase":"asr","sequence":sequence,"segment":segment.model_dump()})

    try:
        translation=await translate_text(source,cfg.translation,cfg.academic,context=translation_context)
        segment.translation=translation
        update_segment(session_id,segment)
        async with send_lock:
            await websocket.send_json({"type":"segment_update","phase":"translation","sequence":sequence,"segment":segment.model_dump()})
    except Exception as exc:
        logger.exception("Translation failed for live segment %s", sequence)
        async with send_lock:
            try: await websocket.send_json({"type":"error","stage":"translation","sequence":sequence,"message":f"Translation: {exc}"})
            except Exception: pass

async def _realtime_partial_worker(websocket: WebSocket, send_lock: asyncio.Lock, session_id: str, cfg: AppConfig, state: dict):
    """Process only the newest provisional speech snapshot; stale snapshots are dropped."""
    while True:
        await state["event"].wait()
        state["event"].clear()
        if state["closed"]:
            return
        result=state.get("latest")
        token=state["token"]
        if result is None:
            continue
        try:
            source,detected=await transcribe_wav(result.wav_bytes,cfg.asr,language=cfg.academic.source_language,prompt=academic_hotwords(cfg.academic))
        except Exception as exc:
            logger.debug("Realtime partial ASR failed: %s", exc)
            continue
        if state["closed"] or token!=state["token"] or state.get("latest") is None:
            continue
        if not source:
            continue
        partial={"source":source,"translation":state.get("translation","") or "","start_ms":result.start_ms,"end_ms":result.end_ms,"language":detected}
        async with send_lock:
            try: await websocket.send_json({"type":"partial","phase":"asr","partial":partial})
            except Exception: return

        due=(result.duration_ms-state.get("last_translation_duration_ms",0))>=cfg.live.partial_translation_interval_ms
        if not due:
            continue
        try:
            translation=await translate_text(source,cfg.translation,cfg.academic,context=_translation_context(session_id,cfg))
        except Exception as exc:
            logger.debug("Realtime partial translation failed: %s", exc)
            continue
        if state["closed"] or token!=state["token"] or state.get("latest") is None:
            continue
        state["translation"]=translation
        state["last_translation_duration_ms"]=result.duration_ms
        partial["translation"]=translation
        async with send_lock:
            try: await websocket.send_json({"type":"partial","phase":"translation","partial":partial})
            except Exception: return

def _new_detector_for_session(session_id: str, cfg: AppConfig|None=None) -> SpeechEndpointDetector:
    cfg=cfg or load_config()
    detector=SpeechEndpointDetector(cfg.live)
    try:
        s=get_session(session_id)
        if s.segments: detector._clock_ms=float(max(seg.end_ms for seg in s.segments))
    except Exception: pass
    return detector

async def _run_pcm_stream(websocket: WebSocket, session_id: str, pcm_source, recorder: SessionAudioRecorder|None=None, send_ready: bool=True):
    cfg=load_config(); detector=_new_detector_for_session(session_id,cfg); send_lock=asyncio.Lock(); tasks:set[asyncio.Task]=set(); sequence=0
    realtime=cfg.live.output_mode=="realtime"
    partial_state={"event":asyncio.Event(),"latest":None,"token":0,"closed":False,"translation":"","last_translation_duration_ms":0}
    partial_task=asyncio.create_task(_realtime_partial_worker(websocket,send_lock,session_id,cfg,partial_state)) if realtime else None
    last_partial_speech_ms: float|None=None
    if send_ready: await websocket.send_json({"type":"ready","session_id":session_id,"output_mode":cfg.live.output_mode})
    try:
        async for pcm in pcm_source:
            if pcm is None: break
            if recorder: recorder.write(pcm)
            level,result=detector.feed(pcm); await websocket.send_json({"type":"level","value":level,"speech":detector.in_speech})
            if result:
                if realtime:
                    partial_state["token"]+=1; partial_state["latest"]=None; partial_state["translation"]=""; partial_state["last_translation_duration_ms"]=0; partial_state["event"].set(); last_partial_speech_ms=None
                sequence+=1; task=asyncio.create_task(_process_live_segment(websocket,send_lock,session_id,result,sequence,cfg)); tasks.add(task); task.add_done_callback(tasks.discard)
                await websocket.send_json({"type":"processing","sequence":sequence,"duration_ms":result.duration_ms})
                continue
            if realtime and detector.in_speech and detector._speech_ms>=cfg.live.realtime_min_audio_ms:
                first_partial=last_partial_speech_ms is None
                interval_due=not first_partial and detector._speech_ms-last_partial_speech_ms>=cfg.live.partial_interval_ms
                if first_partial or interval_due:
                    snapshot=detector.snapshot()
                    if snapshot:
                        partial_state["token"]+=1
                        partial_state["latest"]=snapshot
                        partial_state["event"].set()
                        last_partial_speech_ms=detector._speech_ms
            elif not detector.in_speech:
                last_partial_speech_ms=None
    finally:
        tail=detector.flush()
        if realtime:
            partial_state["token"]+=1; partial_state["latest"]=None; partial_state["translation"]=""; partial_state["event"].set()
        if tail:
            sequence+=1; task=asyncio.create_task(_process_live_segment(websocket,send_lock,session_id,tail,sequence,cfg)); tasks.add(task); task.add_done_callback(tasks.discard)
        if tasks: await asyncio.gather(*list(tasks),return_exceptions=True)
        if partial_task:
            partial_state["closed"]=True; partial_state["token"]+=1; partial_state["event"].set()
            await asyncio.gather(partial_task,return_exceptions=True)
        if recorder:
            filename=await asyncio.to_thread(recorder.close)
            if filename: add_audio_file(session_id,filename)

@app.websocket("/ws/live")
async def live_ws(websocket: WebSocket):
    await websocket.accept(); session_id=websocket.query_params.get("session_id")
    if not session_id: await websocket.close(code=1008); return
    try: get_session(session_id)
    except FileNotFoundError: await websocket.send_json({"type":"error","message":"Session not found"}); await websocket.close(code=1008); return
    cfg=load_config(); recorder=SessionAudioRecorder(session_id,cfg.live.sample_rate,cfg.capture.audio_format) if cfg.capture.save_audio else None
    async def browser_source():
        while True:
            message=await websocket.receive()
            if message.get("bytes") is not None: yield message["bytes"]
            elif message.get("text"):
                try: cmd=json.loads(message["text"])
                except Exception: cmd={}
                if cmd.get("type")=="stop": break
    try: await _run_pcm_stream(websocket,session_id,browser_source(),recorder); await websocket.send_json({"type":"stopped"})
    except WebSocketDisconnect: pass
    finally:
        try: await websocket.close()
        except Exception: pass

@app.websocket("/ws/native")
async def native_ws(websocket: WebSocket):
    await websocket.accept(); session_id=websocket.query_params.get("session_id"); source=websocket.query_params.get("source","native_system"); raw_device=websocket.query_params.get("device")
    if not session_id or raw_device is None: await websocket.send_json({"type":"error","message":"session_id and device are required"}); await websocket.close(code=1008); return
    try: get_session(session_id); device=int(raw_device)
    except Exception: await websocket.send_json({"type":"error","message":"Invalid session or device"}); await websocket.close(code=1008); return
    cfg=load_config(); recorder=SessionAudioRecorder(session_id,cfg.live.sample_rate,cfg.capture.audio_format) if cfg.capture.save_audio else None; queue:asyncio.Queue=asyncio.Queue(maxsize=32); loop=asyncio.get_running_loop(); capture=NativeAudioCapture(device,source=="native_system",loop,queue); capture.start()
    try:
        await asyncio.to_thread(capture.wait_until_ready, 5.0)
    except Exception as exc:
        capture.stop()
        await websocket.send_json({"type":"error","stage":"capture","message":str(exc)})
        await websocket.close(code=1011)
        return
    await websocket.send_json({"type":"ready","session_id":session_id,"output_mode":cfg.live.output_mode})
    async def native_source():
        while True:
            pcm=await queue.get()
            if pcm==b"" and capture.error:
                await websocket.send_json({"type":"error","stage":"capture","message":capture.error})
                yield None
                return
            yield pcm
    task=asyncio.create_task(_run_pcm_stream(websocket,session_id,native_source(),recorder,send_ready=False))
    try:
        while True:
            message=await websocket.receive()
            if message.get("text"):
                try: cmd=json.loads(message["text"])
                except Exception: cmd={}
                if cmd.get("type")=="stop": break
    except WebSocketDisconnect: pass
    finally:
        capture.stop()
        try: queue.put_nowait(None)
        except asyncio.QueueFull: pass
        try: await asyncio.wait_for(task,timeout=8.0)
        except asyncio.TimeoutError: task.cancel()
        except Exception as exc:
            try: await websocket.send_json({"type":"error","message":str(exc)})
            except Exception: pass
        if recorder and not recorder.closed:
            filename=await asyncio.to_thread(recorder.close)
            if filename: add_audio_file(session_id,filename)
        try: await websocket.send_json({"type":"stopped"}); await websocket.close()
        except Exception: pass

@app.get("/api/data-dir")
async def data_dir(): return {"path":str(DATA_DIR)}

@app.on_event("startup")
async def _preload_default_local_asr():
    cfg=load_config()
    if cfg.asr.mode=="local_whisper": await asyncio.to_thread(prepare_local_whisper,cfg.asr)

@app.on_event("shutdown")
async def _shutdown_http_client(): await close_http_client()
