from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import DATA_DIR
from .models import DefenseQATurn
from .store import add_defense_turn, get_session, now_iso

router = APIRouter(prefix="/api/defense", tags=["defense"])

DEFENSE_DIR = DATA_DIR / "defense"
DEFENSE_CONFIG_PATH = DATA_DIR / "defense_config.json"

DEFAULT_SYSTEM_PROMPT = """You are supporting a live PhD viva / thesis defense.

Use the thesis and reference files in the current workspace as the primary source of truth. Search and read the relevant local files before answering. Do not browse the web unless the local materials are genuinely insufficient. Do not modify any files.

Give a direct answer that the candidate can say aloud. Start with the answer itself, not with process commentary. Keep the main response compact (roughly 80–150 words unless the question clearly needs less). Preserve technical terms and construct names exactly. If the local thesis materials do not support a claim, say so briefly instead of inventing evidence.

The original ASR text is the semantic authority; the translation is auxiliary context. Return only the suggested spoken answer and do not describe your search process."""

LEGACY_REASONING_MAP = {
    "fast": "low",
    "balanced": "medium",
    "deep": "high",
}


class DefenseConfig(BaseModel):
    model: str = ""
    reasoning_effort: str = "medium"
    answer_language: Literal["English", "same"] = "English"
    user_prompt: str = ""
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    history_turns: int = Field(default=6, ge=0, le=20)
    timeout_seconds: int = Field(default=90, ge=20, le=300)


class DefenseAskRequest(BaseModel):
    session_id: str = ""
    original: str = ""
    translation: str = ""


class DefenseConfigUpdate(BaseModel):
    model: str = ""
    reasoning_effort: str = "medium"
    answer_language: Literal["English", "same"] = "English"
    user_prompt: str = ""


def _workspace_readme() -> str:
    return """# Academic Live Translator — Defense Q&A workspace

Place the thesis and other defense reference material in this folder before the defense.

Recommended formats: Markdown (`.md`) and plain text (`.txt`). These formats are fast and reliable for Codex to search during live Q&A. If your thesis is a PDF or DOCX, export or convert a searchable copy to Markdown/TXT first.

ALT runs Codex in read-only mode. Codex may inspect files in this folder to answer a selected committee question, but it is not allowed to modify them.
"""


def ensure_defense_workspace() -> Path:
    DEFENSE_DIR.mkdir(parents=True, exist_ok=True)
    readme = DEFENSE_DIR / "README_ALT_DEFENSE.md"
    if not readme.exists():
        readme.write_text(_workspace_readme(), encoding="utf-8")
    return DEFENSE_DIR


def _migrate_defense_config(raw: dict) -> dict:
    migrated = dict(raw)
    if "reasoning_effort" not in migrated:
        migrated["reasoning_effort"] = LEGACY_REASONING_MAP.get(
            str(migrated.get("response_mode", "")).lower(),
            "medium",
        )
    migrated.pop("response_mode", None)
    migrated.setdefault("user_prompt", "")
    migrated.setdefault("system_prompt", DEFAULT_SYSTEM_PROMPT)
    migrated.setdefault("history_turns", 6)
    return migrated


def load_defense_config() -> DefenseConfig:
    if not DEFENSE_CONFIG_PATH.exists():
        cfg = DefenseConfig()
        save_defense_config(cfg)
        return cfg
    try:
        raw = json.loads(DEFENSE_CONFIG_PATH.read_text(encoding="utf-8"))
        cfg = DefenseConfig.model_validate(_migrate_defense_config(raw))
        save_defense_config(cfg)
        return cfg
    except Exception:
        broken = DEFENSE_CONFIG_PATH.with_suffix(".broken.json")
        try:
            DEFENSE_CONFIG_PATH.replace(broken)
        except Exception:
            pass
        cfg = DefenseConfig()
        save_defense_config(cfg)
        return cfg


def save_defense_config(config: DefenseConfig) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEFENSE_CONFIG_PATH.write_text(
        json.dumps(config.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _codex_path() -> str | None:
    return shutil.which("codex") or shutil.which("codex.exe")


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def _codex_configured_model() -> str:
    path = _codex_home() / "config.toml"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^\s*model\s*=\s*["\']([^"\']+)["\']\s*$', text, re.MULTILINE)
        return match.group(1).strip() if match else ""
    except Exception:
        return ""


def _subprocess_flags() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _json_from_output(text: str) -> object:
    text = text.strip()
    if not text:
        raise ValueError("empty JSON output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _normalize_model_catalog(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        raw_models = payload.get("models", [])
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = []

    models: list[dict] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        visibility = item.get("visibility")
        if visibility not in (None, "list"):
            continue
        if item.get("supported_in_api") is False:
            continue
        slug = str(item.get("slug") or item.get("id") or "").strip()
        if not slug:
            continue
        levels: list[dict] = []
        for raw_level in item.get("supported_reasoning_levels") or []:
            if isinstance(raw_level, dict):
                effort = str(raw_level.get("effort") or "").strip()
                description = str(raw_level.get("description") or "").strip()
            else:
                effort = str(raw_level).strip()
                description = ""
            if effort and effort not in {x["effort"] for x in levels}:
                levels.append({"effort": effort, "description": description})
        default_effort = str(item.get("default_reasoning_level") or "").strip()
        if default_effort and default_effort not in {x["effort"] for x in levels}:
            levels.append({"effort": default_effort, "description": ""})
        models.append({
            "slug": slug,
            "display_name": str(item.get("display_name") or slug),
            "description": str(item.get("description") or ""),
            "default_reasoning_level": default_effort or (levels[0]["effort"] if levels else "medium"),
            "supported_reasoning_levels": levels,
            "priority": int(item.get("priority") or 9999),
        })
    models.sort(key=lambda x: (x["priority"], x["display_name"].lower()))
    return models


def codex_model_catalog() -> dict:
    codex = _codex_path()
    source = "none"
    payload: object = {}

    if codex:
        try:
            proc = subprocess.run(
                [codex, "debug", "models"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
                **_subprocess_flags(),
            )
            if proc.returncode == 0:
                payload = _json_from_output(proc.stdout or proc.stderr)
                source = "codex-debug"
        except Exception:
            payload = {}

    if not _normalize_model_catalog(payload):
        cache = _codex_home() / "models_cache.json"
        if cache.exists():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8", errors="replace"))
                source = "models-cache"
            except Exception:
                payload = {}

    return {
        "models": _normalize_model_catalog(payload),
        "current_model": _codex_configured_model(),
        "source": source,
    }


def codex_status() -> dict:
    workspace = ensure_defense_workspace()
    codex = _codex_path()
    files = [
        p.name
        for p in workspace.iterdir()
        if p.is_file() and p.name != "README_ALT_DEFENSE.md"
    ]
    result = {
        "installed": bool(codex),
        "authenticated": False,
        "version": "",
        "workspace": str(workspace),
        "reference_files": sorted(files),
        "current_model": _codex_configured_model(),
    }
    if not codex:
        return result

    try:
        proc = subprocess.run(
            [codex, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
            **_subprocess_flags(),
        )
        if proc.returncode == 0:
            result["version"] = (proc.stdout or proc.stderr).strip().splitlines()[0]
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [codex, "login", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            check=False,
            **_subprocess_flags(),
        )
        result["authenticated"] = proc.returncode == 0
    except Exception:
        result["authenticated"] = False
    return result


def _history_block(history: list[DefenseQATurn], limit: int) -> str:
    if not history or limit <= 0:
        return "(none)"
    rows: list[str] = []
    for index, turn in enumerate(history[-limit:], 1):
        question = turn.original.strip() or turn.translation.strip()
        rows.append(f"Q{index}: {question}\nA{index}: {turn.answer.strip()}")
    return "\n\n".join(rows)


def build_defense_prompt(
    original: str,
    translation: str,
    config: DefenseConfig,
    history: list[DefenseQATurn] | None = None,
) -> str:
    original = original.strip()
    translation = translation.strip()
    language_instruction = (
        "Answer in concise spoken academic English."
        if config.answer_language == "English"
        else "Answer in the same language as the committee question."
    )
    user_prompt = config.user_prompt.strip() or "(none)"
    return f"""SYSTEM PROMPT:
{config.system_prompt.strip()}

USER PROMPT:
{user_prompt}

RUNTIME REQUIREMENTS:
{language_instruction}
Treat the previous Q&A as conversational context for follow-up questions. The current question has priority if it conflicts with earlier turns.

PREVIOUS DEFENSE Q&A:
{_history_block(history or [], config.history_turns)}

CURRENT ORIGINAL QUESTION:
{original or "(not available)"}

CURRENT TRANSLATION:
{translation or "(not available)"}
"""


def run_codex_answer(
    original: str,
    translation: str,
    config: DefenseConfig,
    history: list[DefenseQATurn] | None = None,
) -> dict:
    codex = _codex_path()
    if not codex:
        raise RuntimeError("Codex CLI is not installed. Install it with: npm install -g @openai/codex")

    workspace = ensure_defense_workspace()
    command = [
        codex,
        "--ask-for-approval",
        "never",
        "exec",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
    ]
    if config.reasoning_effort.strip():
        command.extend(["--config", f"model_reasoning_effort={config.reasoning_effort.strip()}"])
    if config.model.strip():
        command.extend(["--model", config.model.strip()])
    command.append("-")

    prompt = build_defense_prompt(original, translation, config, history)
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            input=prompt,
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.timeout_seconds,
            check=False,
            **_subprocess_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Codex timed out after {config.timeout_seconds} seconds") from exc

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "Codex exited with an unknown error").strip()
        if len(message) > 1800:
            message = message[-1800:]
        raise RuntimeError(message)

    answer = proc.stdout.strip()
    if not answer:
        raise RuntimeError("Codex returned an empty answer")
    return {
        "answer": answer,
        "duration_ms": elapsed_ms,
        "reasoning_effort": config.reasoning_effort,
        "model": config.model.strip() or "auto",
    }


@router.get("/config")
async def get_defense_config():
    cfg = load_defense_config()
    public = cfg.model_dump(exclude={"system_prompt"})
    return {
        **public,
        "workspace": str(ensure_defense_workspace()),
        "config_path": str(DEFENSE_CONFIG_PATH),
        "system_prompt_configured": bool(cfg.system_prompt.strip()),
    }


@router.put("/config")
async def update_defense_config(req: DefenseConfigUpdate):
    current = load_defense_config()
    cfg = DefenseConfig(
        model=req.model.strip(),
        reasoning_effort=req.reasoning_effort.strip() or current.reasoning_effort,
        answer_language=req.answer_language,
        user_prompt=req.user_prompt,
        system_prompt=current.system_prompt,
        history_turns=current.history_turns,
        timeout_seconds=current.timeout_seconds,
    )
    save_defense_config(cfg)
    public = cfg.model_dump(exclude={"system_prompt"})
    return {
        **public,
        "workspace": str(ensure_defense_workspace()),
        "config_path": str(DEFENSE_CONFIG_PATH),
        "system_prompt_configured": bool(cfg.system_prompt.strip()),
    }


@router.get("/models")
async def get_defense_models():
    return await asyncio.to_thread(codex_model_catalog)


@router.get("/status")
async def get_defense_status():
    return await asyncio.to_thread(codex_status)


@router.get("/history/{session_id}")
async def get_defense_history(session_id: str):
    try:
        session = get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")
    return {"session_id": session.id, "turns": [turn.model_dump() for turn in session.defense_qa]}


@router.post("/open-workspace")
async def open_defense_workspace():
    workspace = ensure_defense_workspace()
    try:
        if sys.platform == "win32":
            os.startfile(str(workspace))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(workspace)])
        else:
            subprocess.Popen(["xdg-open", str(workspace)])
    except Exception as exc:
        raise HTTPException(500, f"Could not open Defense workspace: {exc}") from exc
    return {"ok": True, "workspace": str(workspace)}


@router.post("/ask")
async def ask_defense(req: DefenseAskRequest):
    session_id = req.session_id.strip()
    original = req.original.strip()
    translation = req.translation.strip()
    if not session_id:
        raise HTTPException(400, "Open or create an ALT session before asking Codex")
    if not original and not translation:
        raise HTTPException(400, "Select at least one transcript segment before asking Codex")
    if len(original) + len(translation) > 24000:
        raise HTTPException(400, "Selected question is too long; select fewer transcript segments")

    try:
        session = get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

    cfg = load_defense_config()
    history = session.defense_qa[-cfg.history_turns:] if cfg.history_turns else []
    try:
        result = await asyncio.to_thread(run_codex_answer, original, translation, cfg, history)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

    turn = DefenseQATurn(
        id=uuid.uuid4().hex[:10],
        original=original,
        translation=translation,
        answer=result["answer"],
        model=result["model"],
        reasoning_effort=result["reasoning_effort"],
        duration_ms=result["duration_ms"],
        created_at=now_iso(),
    )
    updated = add_defense_turn(session_id, turn)
    return {**result, "turn": turn.model_dump(), "history_count": len(updated.defense_qa)}
