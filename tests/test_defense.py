import subprocess

from app.defense import DefenseConfig, _normalize_model_catalog, build_defense_prompt, run_codex_answer
from app.models import DefenseQATurn


def test_defense_prompt_combines_system_user_question_and_history():
    history = [
        DefenseQATurn(
            id="turn1",
            original="Why did you use PLS-SEM?",
            translation="为什么使用 PLS-SEM？",
            answer="Because the model is prediction-oriented.",
            created_at="2026-10-13T00:00:00+00:00",
        )
    ]
    prompt = build_defense_prompt(
        "Why not CB-SEM?",
        "为什么不用 CB-SEM？",
        DefenseConfig(
            reasoning_effort="high",
            answer_language="English",
            system_prompt="SYSTEM RULE",
            user_prompt="Keep the answer under 60 seconds.",
        ),
        history,
    )
    assert "SYSTEM PROMPT" in prompt
    assert "SYSTEM RULE" in prompt
    assert "USER PROMPT" in prompt
    assert "Keep the answer under 60 seconds." in prompt
    assert "PREVIOUS DEFENSE Q&A" in prompt
    assert "Why did you use PLS-SEM?" in prompt
    assert "CURRENT ORIGINAL QUESTION" in prompt
    assert "Why not CB-SEM?" in prompt
    assert "spoken academic English" in prompt


def test_codex_reasoning_effort_is_passed_directly(monkeypatch, tmp_path):
    monkeypatch.setattr("app.defense._codex_path", lambda: "codex")
    monkeypatch.setattr("app.defense.ensure_defense_workspace", lambda: tmp_path)
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "A concise viva answer.", "")

    monkeypatch.setattr("app.defense.subprocess.run", fake_run)
    result = run_codex_answer(
        "Question",
        "问题",
        DefenseConfig(model="gpt-test", reasoning_effort="xhigh"),
    )

    assert "--sandbox" in captured["command"]
    assert "read-only" in captured["command"]
    assert "--ask-for-approval" in captured["command"]
    assert "never" in captured["command"]
    assert "model_reasoning_effort=xhigh" in captured["command"]
    assert "--model" in captured["command"]
    assert "gpt-test" in captured["command"]
    assert captured["kwargs"]["cwd"] == tmp_path
    assert result["answer"] == "A concise viva answer."
    assert result["reasoning_effort"] == "xhigh"


def test_model_catalog_uses_model_supported_reasoning_levels():
    models = _normalize_model_catalog({
        "models": [
            {
                "slug": "gpt-test",
                "display_name": "GPT Test",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 1,
                "default_reasoning_level": "medium",
                "supported_reasoning_levels": [
                    {"effort": "low", "description": "fast"},
                    {"effort": "medium", "description": "balanced"},
                    {"effort": "high", "description": "deep"},
                    {"effort": "xhigh", "description": "extra"},
                    {"effort": "max", "description": "maximum"},
                    {"effort": "ultra", "description": "delegated maximum"},
                ],
            },
            {
                "slug": "hidden-model",
                "display_name": "Hidden",
                "visibility": "none",
                "supported_in_api": True,
                "priority": 0,
                "supported_reasoning_levels": [],
            },
        ]
    })

    assert [model["slug"] for model in models] == ["gpt-test"]
    assert [level["effort"] for level in models[0]["supported_reasoning_levels"]] == [
        "low", "medium", "high", "xhigh", "max", "ultra"
    ]
