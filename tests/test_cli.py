import os
import subprocess
import sys

import pytest

from airchinstall import app
from airchinstall.app import export_transcript


def test_public_cli_exposes_only_start_doctor_and_export():
    completed = subprocess.run(
        [sys.executable, "-m", "airchinstall", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "start" in completed.stdout
    assert "doctor" in completed.stdout
    assert "export-transcript" in completed.stdout
    assert "_daemon" not in completed.stdout


def test_export_transcript_redacts_again_and_writes_mode_600(tmp_path):
    runtime = tmp_path / "run"
    runtime.mkdir()
    (runtime / "transcript.jsonl").write_text(
        '{"command":"echo ok","output_excerpt":"OPENAI_API_KEY=sk-export-secret"}\n'
    )
    destination = tmp_path / "export.jsonl"

    export_transcript(runtime, destination)

    assert "sk-export-secret" not in destination.read_text()
    assert destination.read_text().count("[REDACTED]") == 1
    assert os.stat(destination).st_mode & 0o777 == 0o600


def test_start_refuses_guided_mode_when_preflight_fails(tmp_path, monkeypatch):
    async def failed_doctor(_runtime):
        return [("Cloud AI", False, "TutorUnavailable")]

    monkeypatch.setattr(app, "_doctor", failed_doctor)
    monkeypatch.setattr(
        app,
        "create_tmux_session",
        lambda _runtime: pytest.fail("tmux must not start after failed preflight"),
    )

    with pytest.raises(SystemExit) as exit_info:
        app.start_session(tmp_path)

    assert exit_info.value.code == 1
