"""Cross-repo contract: the molcrafts-harness hook, driven against the real ``molab``.

``../molcrafts-harness/hooks/molab_guard.py`` holds no rule; it forwards each
Claude Code event to ``molab check`` and turns the verdict into the hook's
answer. This test pipes real PreToolUse / SessionStart / Stop events through
that file with this checkout's ``molab`` first on ``PATH``, so a change to the
argv or the Verdict JSON that breaks the hook fails here.

Skipped when the sibling checkout is absent or ``molab`` cannot start in this
environment. The subprocess inherits ``os.environ`` (``PYTHONPATH`` included).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from molab import frontmatter
from molab.workspace import Workspace

GUARD = (
    Path(__file__).resolve().parents[2].parent / "molcrafts-harness" / "hooks" / "molab_guard.py"
)
MOLAB = Path(sys.executable).parent / "molab"


def _env() -> dict[str, str]:
    return {**os.environ, "PATH": f"{MOLAB.parent}{os.pathsep}{os.environ.get('PATH', '')}"}


@pytest.fixture(scope="module")
def guard() -> Path:
    if not GUARD.is_file():
        pytest.skip(f"sibling harness checkout absent: {GUARD}")
    if not MOLAB.is_file():
        pytest.skip(f"no molab executable beside {sys.executable}")
    probe = subprocess.run(
        [str(MOLAB), "--version"], capture_output=True, text=True, env=_env(), check=False
    )
    if probe.returncode != 0:
        pytest.skip(f"molab cannot start here: {probe.stderr.strip()[-200:]}")
    return GUARD


def _hook(guard: Path, mode: str, event: dict[str, Any]) -> dict[str, Any] | None:
    done = subprocess.run(
        [sys.executable, str(guard), mode],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=_env(),
        check=True,
        timeout=120,
    )
    return json.loads(done.stdout) if done.stdout.strip() else None


@pytest.fixture(autouse=True)
def _isolated_hook_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook keeps per-session state under ``$XDG_CACHE_HOME/molab-guard``.

    A shared cache lets a fixed session id carry roots from earlier test runs
    (pytest keeps recent temp dirs), so a later ``stop`` re-checks an old lab.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def lab(tmp_path: Path) -> Path:
    ws = Workspace(tmp_path / "lab")
    ws.materialize()
    run = ws.add_project("p").add_experiment("e").add_run(params={"t": 1})
    run_dir = Path(str(run.resolve()))
    run_dir.rename(run_dir.parent / "x")
    return Path(str(ws.resolve()))


def _write_event(path: Path, content: str, cwd: Path) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "contract",
        "cwd": str(cwd),
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": content},
    }


def test_an_edited_record_frontmatter_is_denied(guard: Path, lab: Path) -> None:
    index = lab / "projects" / "p" / "experiments" / "e" / "runs" / "x" / "index.md"
    meta, body = frontmatter.split(index.read_text())
    meta["parameters"] = {"t": 2}

    answer = _hook(guard, "pre", _write_event(index, frontmatter.dump(meta, body), lab))

    assert answer is not None
    out = answer["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    assert "molab index write -p p -e e --run x" in out["permissionDecisionReason"]


def test_a_body_only_edit_passes(guard: Path, lab: Path) -> None:
    index = lab / "projects" / "p" / "experiments" / "e" / "runs" / "x" / "index.md"
    meta, body = frontmatter.split(index.read_text())

    answer = _hook(guard, "pre", _write_event(index, frontmatter.dump(meta, body + "notes\n"), lab))

    assert answer is None


def test_a_session_is_held_to_what_it_added(guard: Path, lab: Path) -> None:
    session = {"session_id": "contract-session", "cwd": str(lab)}
    (lab / "projects" / "p" / "old.txt").write_text("old debt")

    assert _hook(guard, "start", session) is None
    assert _hook(guard, "stop", session) is None

    (lab / "projects" / "p" / "experiments" / "e" / "analysis.py").write_text("x")
    answer = _hook(guard, "stop", session)

    assert answer is not None and answer["decision"] == "block"
    assert "layout.stray" in answer["reason"]
    assert "analysis.py" in answer["reason"]
    assert "old.txt" not in answer["reason"]
