"""``molab.workspace.env_clean``: environment directories are not the experiment.

A virtual environment, bytecode and tool caches are rebuilt from the code; a
workspace holds them only because work was done in it. The plan names every
such directory (it never descends into one, nor into ``.git`` / ``.molab``)
and the apply removes exactly what the plan names.
"""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.env_clean import apply_env_clean, plan_env_clean


def _workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "ws")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e", params={})
    root = Path(str(ws.root))
    exp_dir = Path(str(exp.path))
    for rel in (
        ".venv/bin/python",
        ".venv-x86_64/lib/x.py",
        ".ruff_cache/0.1/x",
        "src/__pycache__/m.cpython-312.pyc",
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x")
    for rel in ("__pycache__/w.pyc", ".pytest_cache/v", "workflow.py", "scratch/note.txt"):
        (exp_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (exp_dir / rel).write_text("x")
    (root / ".git" / "objects" / "__pycache__").mkdir(parents=True)
    (root / ".molab" / "locks" / "__pycache__").mkdir(parents=True)
    return ws


def test_plan_names_every_environment_directory_and_writes_nothing(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    exp = "projects/p/experiments/e"

    plan = plan_env_clean(ws)

    assert plan == (
        ".ruff_cache",
        ".venv",
        ".venv-x86_64",
        f"{exp}/.pytest_cache",
        f"{exp}/__pycache__",
        "src/__pycache__",
    )
    assert (Path(str(ws.root)) / ".venv" / "bin" / "python").exists()


def test_apply_removes_the_plan_and_keeps_the_experiment(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    root = Path(str(ws.root))

    assert apply_env_clean(ws, plan_env_clean(ws)) == 6
    assert plan_env_clean(ws) == ()
    assert (root / "projects/p/experiments/e/workflow.py").exists()
    assert (root / "projects/p/experiments/e/scratch/note.txt").exists()
    assert (root / ".git" / "objects" / "__pycache__").exists()


def test_apply_refuses_a_path_that_is_not_an_environment_directory(tmp_path: Path) -> None:
    import pytest

    ws = _workspace(tmp_path)

    with pytest.raises(ValueError, match="not an environment directory"):
        apply_env_clean(ws, ("projects/p/experiments/e",))
    assert (Path(str(ws.root)) / "projects/p/experiments/e/workflow.py").exists()


def test_a_link_is_neither_entered_nor_removed(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    outside = tmp_path / "outside" / "__pycache__"
    outside.mkdir(parents=True)
    (Path(str(ws.root)) / "linked").symlink_to(tmp_path / "outside")
    (Path(str(ws.root)) / "__pycache__").symlink_to(outside)

    plan = plan_env_clean(ws)

    assert "__pycache__" not in plan
    assert not any(rel.startswith("linked/") for rel in plan)
