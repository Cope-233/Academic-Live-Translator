from __future__ import annotations
import json, shutil, uuid
from datetime import datetime, timezone
from .config import SESSIONS_DIR, session_assets_dir
from .models import Annotation, DefenseQATurn, ScreenshotAsset, Segment, SessionData

def now_iso(): return datetime.now(timezone.utc).isoformat()
def _path(session_id:str): return SESSIONS_DIR/f"{session_id}.json"
def save_session(s:SessionData): s.updated_at=now_iso(); _path(s.id).write_text(json.dumps(s.model_dump(),ensure_ascii=False,indent=2),encoding='utf-8')
def create_session(title=None,source_language='auto',target_language='Chinese',mode='live',input_source='microphone'):
    sid=uuid.uuid4().hex[:12]; now=now_iso(); s=SessionData(id=sid,title=title or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",created_at=now,updated_at=now,source_language=source_language,target_language=target_language,mode=mode,input_source=input_source); save_session(s); return s
def get_session(session_id:str):
    p=_path(session_id)
    if not p.exists(): raise FileNotFoundError(session_id)
    return SessionData.model_validate(json.loads(p.read_text(encoding='utf-8')))
def list_sessions(query=''):
    items=[]; q=query.strip().lower()
    for p in SESSIONS_DIR.glob('*.json'):
        try:
            s=SessionData.model_validate(json.loads(p.read_text(encoding='utf-8')))
            qa_text=[turn.original+' '+turn.translation+' '+turn.answer for turn in s.defense_qa]
            hay=' '.join([s.title]+[x.source+' '+x.translation for x in s.segments]+[a.text for a in s.annotations]+qa_text).lower()
            if not q or q in hay: items.append(s)
        except Exception: pass
    return sorted(items,key=lambda x:x.updated_at,reverse=True)
def append_segment(session_id,segment): s=get_session(session_id); s.segments.append(segment); s.segments.sort(key=lambda x:(x.start_ms,x.end_ms,x.id)); save_session(s); return s
def update_segment(session_id,segment):
    s=get_session(session_id)
    for i,current in enumerate(s.segments):
        if current.id==segment.id:
            s.segments[i]=segment; s.segments.sort(key=lambda x:(x.start_ms,x.end_ms,x.id)); save_session(s); return s
    s.segments.append(segment); s.segments.sort(key=lambda x:(x.start_ms,x.end_ms,x.id)); save_session(s); return s
def set_bookmark(session_id,segment_id,bookmarked):
    s=get_session(session_id)
    for seg in s.segments:
        if seg.id==segment_id: seg.bookmarked=bookmarked; save_session(s); return s
    raise KeyError(segment_id)
def patch_title(session_id,title): s=get_session(session_id); s.title=title.strip() or s.title; save_session(s); return s
def add_annotation(session_id,annotation:Annotation): s=get_session(session_id); s.annotations.append(annotation); s.annotations.sort(key=lambda x:(x.timestamp_ms,x.created_at)); save_session(s); return s
def add_screenshot(session_id,shot:ScreenshotAsset): s=get_session(session_id); s.screenshots.append(shot); s.screenshots.sort(key=lambda x:(x.timestamp_ms,x.created_at)); save_session(s); return s
def add_audio_file(session_id,filename): s=get_session(session_id); (s.audio_files.append(filename) if filename not in s.audio_files else None); save_session(s); return s
def add_defense_turn(session_id,turn:DefenseQATurn):
    s=get_session(session_id); s.defense_qa.append(turn); save_session(s); return s
def delete_session(session_id):
    p=_path(session_id)
    if not p.exists(): raise FileNotFoundError(session_id)
    p.unlink(); assets=session_assets_dir(session_id); shutil.rmtree(assets,ignore_errors=True)
