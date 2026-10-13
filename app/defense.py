from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import DATA_DIR

router = APIRouter(prefix="/api/defense", tags=["defense"])

DEFENSE_DIR = DATA_DIR / "defense"
DEFENSE_CONFIG_PATH = DATA_DIR / "defense_config.json"


class DefenseConfig(BaseModel):
    response_mode: Literal["fast", "balanced", "deep"] = "fast"
    answer_language: Literal["English", "same"] = "English"
    model: str = ""
    timeout_seconds: int = Field(default=90, ge=20, le=300)


class DefenseAskRequest(BaseModel):
    original: str = ""
    translation: str = ""


class DefenseConfigUpdate(BaseModel):
    response_mode: Literal["fast", "balanced", "deep"] = "fast"
    answer_language: Literal["English", "same"] = "English"
    model: str = ""


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


def load_defense_config() -> DefenseConfig:
    if not DEFENSE_CONFIG_PATH.exists():
        cfg = DefenseConfig()
        save_defense_config(cfg)
        return cfg
    try:
        return DefenseConfig.model_validate_json(DEFENSE_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
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


def _subprocess_flags() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


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


def build_defense_prompt(original: str, translation: str, config: DefenseConfig) -> str:
    original = original.strip()
    translation = translation.strip()
    language_instruction = (
        "Answer in concise spoken academic English."
        if config.answer_language == "English"
        else "Answer in the same language as the committee question."
    )
    return f"""You are supporting a live PhD viva / thesis defense.

Use the thesis and reference files in the current workspace as the primary source of truth. Search and read the relevant local files before answering. Do not browse the web unless the local materials are genuinely insufficient. Do not modify any files.

Give a direct answer that the candidate can say aloud. Start with the answer itself, not with process commentary. Keep the main response compact (roughly 80–150 words unless the question clearly needs less). Preserve technical terms and construct names exactly. If the local thesis materials do not support a claim, say so briefly instead of inventing evidence. {language_instruction}

The original ASR text is the semantic authority; the translation is auxiliary context.

ORIGINAL QUESTION:
{original or "(not available)"}

TRANSLATION:
{translation or "(not available)"}

Return only the suggested spoken answer. Do not describe your search process.
"""


def run_codex_answer(original: str, translation: str, config: DefenseConfig) -> dict:
    codex = _codex_path()
    if not codex:
        raise RuntimeError("Codex CLI is not installed. Install it with: npm install -g @openai/codex")

    workspace = ensure_defense_workspace()
    effort = {"fast": "low", "balanced": "medium", "deep": "high"}[config.response_mode]
    command = [
        codex,
        "exec",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "--skip-git-repo-check",
        "--config",
        f"model_reasoning_effort={effort}",
    ]
    if config.model.strip():
        command.extend(["--model", config.model.strip()])
    command.append("-")

    prompt = build_defense_prompt(original, translation, config)
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
        "response_mode": config.response_mode,
        "model": config.model.strip() or "auto",
    }


@router.get("/config")
async def get_defense_config():
    cfg = load_defense_config()
    return {**cfg.model_dump(), "workspace": str(ensure_defense_workspace())}


@router.put("/config")
async def update_defense_config(req: DefenseConfigUpdate):
    current = load_defense_config()
    cfg = DefenseConfig(
        response_mode=req.response_mode,
        answer_language=req.answer_language,
        model=req.model.strip(),
        timeout_seconds=current.timeout_seconds,
    )
    save_defense_config(cfg)
    return {**cfg.model_dump(), "workspace": str(ensure_defense_workspace())}


@router.get("/status")
async def get_defense_status():
    return await asyncio.to_thread(codex_status)


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
    original = req.original.strip()
    translation = req.translation.strip()
    if not original and not translation:
        raise HTTPException(400, "Select at least one transcript segment before asking Codex")
    if len(original) + len(translation) > 24000:
        raise HTTPException(400, "Selected question is too long; select fewer transcript segments")

    cfg = load_defense_config()
    try:
        return await asyncio.to_thread(run_codex_answer, original, translation, cfg)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
