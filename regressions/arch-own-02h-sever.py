"""Public-API goldens for arch-own-02h-sever.

An attempt's provenance and config have one home (its ``execution.json``) and
one creator (``Run.create_execution``):

1. ``run.start(execution_id=...)`` on an id nothing created raises
   ``ValueError``; it no longer creates the record.
2. Passing a creation argument (``bypass_cache=True``) with an explicit id
   raises ``ValueError``.
3. A ``profile_config`` that differs from the recorded one raises
   ``ValueError``.
4. The preallocated QUEUED ``e01`` starts, runs with the recorded config and
   seals as ``succeeded``.
5. ``Run.update_provenance`` is gone, ``RunMetadata`` has none of the seven
   run-level provenance fields, a legacy ``run.json`` carrying them still
   loads, and no run-level ``source/`` directory is written.

Expected stdout (exactly these lines, exit code 0):

    unknown execution id: ValueError
    creation args with explicit id: ValueError
    differing profile_config with explicit id: ValueError
    queued e01 started: e01 succeeded config=cpu {'k': 1}
    Run.update_provenance: absent
    RunMetadata provenance fields: []
    legacy run.json loads: r
    run-level source/: absent
    arch-own-02h-sever: ok

Provenance: goldens hard-coded from the spec
``.claude/specs/arch-own-02h-sever.md`` (Testing strategy, "回归示例") and
molab's own behaviour (no third-party oracle), recorded 2026-09-29 on branch
feat/knowledge-crossref. The workspace is an in-process temporary directory —
no subprocess, no network, no third-party runtime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.profile import ProfileConfig
from molab.workspace import Run, Workspace
from molab.workspace.models import RunMetadata

_PROVENANCE_FIELDS = (
    "script",
    "source_snapshot",
    "submit_cwd",
    "profile",
    "config",
    "config_hash",
    "executor_info",
)


def _raises(label: str, fn: object) -> None:
    try:
        fn()  # type: ignore[operator]
    except ValueError:
        print(f"{label}: ValueError")
        return
    raise AssertionError(f"{label}: expected ValueError")


def _check(root: Path) -> None:
    scripts = {}
    for name in ("a", "b", "c"):
        (root / name).mkdir()
        scripts[name] = root / name / "main.py"
        scripts[name].write_text(f"VALUE = {name!r}\n", encoding="utf-8")

    ws = Workspace(root=root / "lab", name="Lab")
    exp = ws.add_project("p").add_experiment("e")
    r1, r2, r3 = (exp.add_run(params={"seed": i}) for i in (1, 2, 3))
    r1.create_execution(
        source_entrypoint=scripts["a"], profile_config=ProfileConfig({"k": 1}, name="cpu")
    )
    r2.create_execution(source_entrypoint=scripts["b"])
    r3.create_execution(source_entrypoint=scripts["c"])

    def _enter(run: Run, *args: object, **kwargs: object) -> None:
        with run.start(*args, **kwargs):  # type: ignore[arg-type]
            pass

    _raises("unknown execution id", lambda: _enter(r3, execution_id="e09"))
    _raises(
        "creation args with explicit id",
        lambda: _enter(r1, execution_id="e01", bypass_cache=True),
    )
    _raises(
        "differing profile_config with explicit id",
        lambda: _enter(r1, ProfileConfig({"k": 2}, name="cpu"), execution_id="e01"),
    )

    with r1.start(execution_id="e01") as ctx:
        name, data = ctx.config.name, ctx.config.to_dict()
    e01 = r1.execution("e01")
    print(f"queued e01 started: {e01.id} {e01.status.value} config={name} {data}")

    print(f"Run.update_provenance: {'present' if hasattr(r1, 'update_provenance') else 'absent'}")
    left = [f for f in _PROVENANCE_FIELDS if f in RunMetadata.model_fields]
    print(f"RunMetadata provenance fields: {left}")
    legacy = RunMetadata.model_validate(
        {
            "id": "r",
            "definition_hash": "h",
            "experiment_revision_id": "rev",
            "script": "/x.py",
            "source_snapshot": {"dir": "source"},
            "submit_cwd": "/tmp",
            "profile": "cpu",
            "config": {"cpus": 8},
            "config_hash": "abc",
            "executor_info": {"job_id": "j"},
        }
    )
    print(f"legacy run.json loads: {legacy.id}")
    source = Path(str(r1.run_dir)) / "source"
    print(f"run-level source/: {'present' if source.exists() else 'absent'}")
    print("arch-own-02h-sever: ok")


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        _check(Path(raw))


if __name__ == "__main__":
    main()
