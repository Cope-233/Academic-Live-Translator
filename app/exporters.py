from __future__ import annotations
import json
from .models import SessionData

def ts(ms:int,srt:bool=False)->str:
    total,millis=divmod(max(0,ms),1000); h,rem=divmod(total,3600); m,s=divmod(rem,60); sep=',' if srt else '.'
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{millis:03d}"
def export_txt(session:SessionData)->str:
    out=[session.title,f"Mode: {session.mode} | Input: {session.input_source}",""]
    for seg in session.segments:
        out += [f"[{ts(seg.start_ms)}] {seg.source}"] + ([seg.translation] if seg.translation else []) + [""]
    if session.annotations:
        out += ["--- Notes & Marks ---",""]+[f"[{ts(a.timestamp_ms)}] {a.kind}: {a.text}" for a in session.annotations]
    if session.defense_qa:
        out += ["", "--- Defense Q&A ---", ""]
        for i,turn in enumerate(session.defense_qa,1):
            question=turn.translation or turn.original
            out += [f"Q{i}: {question}", f"A{i}: {turn.answer}", f"Model: {turn.model} | Reasoning: {turn.reasoning_effort}", ""]
    return "\n".join(out).rstrip()+"\n"
def export_markdown(session:SessionData)->str:
    out=[f"# {session.title}","",f"- Mode: `{session.mode}`",f"- Input: `{session.input_source}`",f"- Languages: `{session.source_language}` → `{session.target_language}`",""]
    for seg in session.segments:
        out += [f"## {ts(seg.start_ms)}"+(" ⭐" if seg.bookmarked else ""),"","**Original**","",seg.source,""]
        if seg.translation: out += ["**Translation**","",seg.translation,""]
    if session.annotations:
        out += ["# Notes & Marks",""]
        for a in session.annotations: out += [f"## {ts(a.timestamp_ms)} · {a.kind.replace('_',' ').title()}","",a.text or "(marked)",""]
    if session.defense_qa:
        out += ["# Defense Q&A",""]
        for i,turn in enumerate(session.defense_qa,1):
            out += [f"## Q{i}",""]
            if turn.original: out += ["**Original question**","",turn.original,""]
            if turn.translation: out += ["**Translation**","",turn.translation,""]
            out += ["**Suggested answer**","",turn.answer,"",f"`{turn.model}` · `{turn.reasoning_effort}` · {turn.duration_ms/1000:.1f}s",""]
    if session.screenshots: out += ["# Slides / Screenshots",""]+[f"- {ts(s.timestamp_ms)} · `{s.filename}`{(' · '+s.note) if s.note else ''}" for s in session.screenshots]+[""]
    if session.audio_files: out += ["# Session Audio",""]+[f"- `{x}`" for x in session.audio_files]+[""]
    return "\n".join(out).rstrip()+"\n"
def export_srt(session:SessionData,translated:bool=False)->str:
    return "\n".join(f"{i}\n{ts(seg.start_ms,True)} --> {ts(seg.end_ms,True)}\n{seg.translation if translated and seg.translation else seg.source}\n" for i,seg in enumerate(session.segments,1))
def export_json(session:SessionData)->str: return json.dumps(session.model_dump(),ensure_ascii=False,indent=2)+"\n"
