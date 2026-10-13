import subprocess

from app.defense import DefenseConfig, build_defense_prompt, run_codex_answer


def test_defense_prompt_uses_original_as_authority():
    prompt = build_defense_prompt(
        "Why did you choose PLS-SEM?",
        "为什么选择 PLS-SEM？",
        DefenseConfig(response_mode="fast", answer_language="English"),
    )
    assert "ORIGINAL QUESTION" in prompt
    assert "Why did you choose PLS-SEM?" in prompt
    assert "TRANSLATION" in prompt
    assert "spoken academic English" in prompt
    assert "Do not modify any files" in prompt


def test_codex_fast_mode_maps_to_low_reasoning(monkeypatch, tmp_path):
    monkeypatch.setattr("app.defense._codex_path", lambda: "codex")
    monkeypatch.setattr("app.defense.ensure_defense_workspace", lambda: tmp_path)
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "A concise viva answer.", "")

    monkeypatch.setattr("app.defense.subprocess.run", fake_run)
    result = run_codex_answer("Question", "问题", DefenseConfig(response_mode="fast"))

    assert "--sandbox" in captured["command"]
    assert "read-only" in captured["command"]
    assert "--ask-for-approval" in captured["command"]
    assert "never" in captured["command"]
    assert "model_reasoning_effort=low" in captured["command"]
    assert captured["kwargs"]["cwd"] == tmp_path
    assert result["answer"] == "A concise viva answer."
