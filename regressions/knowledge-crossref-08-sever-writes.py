"""Public-API goldens for knowledge-crossref-08-sever-writes.

Hard-coded: the six ``molab.workspace`` knowledge modules are *absent*
(``find_spec`` is ``None``), the 9 severed ``__all__`` names plus the
non-``__all__`` re-export ``summarize_entity`` are unreachable on
``molab.workspace``, ``molab.knowledge`` still exports its eight public names,
and a workspace built through the public API lands its run exactly where the
layout law says. Uses ``molab.workspace`` / ``molab.knowledge`` only — no
third-party runtime.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import molab.knowledge
import molab.workspace


def main() -> None:
    # ── the six modules are gone, and gone for real ──────────────────────────
    for module in (
        "molab.workspace.knowledge",
        "molab.workspace.knowledge_write",
        "molab.workspace.knowledge_mount",
        "molab.workspace.harvest",
        "molab.workspace.doc_embed",
        "molab.workspace.bundle",
    ):
        assert importlib.util.find_spec(module) is None, module

    # ── the workspace's knowledge names are unreachable ──────────────────────
    for name in (
        "PLAN_BOOK_NAME",
        "EntitySummary",
        "Finding",
        "Knowledge",
        "Observation",
        "Plan",
        "Report",
        "SourceKind",
        "SourceRef",
    ):
        assert not hasattr(molab.workspace, name), name
        assert name not in molab.workspace.__all__, name
    assert not hasattr(molab.workspace, "summarize_entity")
    # 91 at this cut; knowledge-crossref-09 shed the nine knowledge names the
    # workspace's forwarder shells had carried, leaving 82.
    assert (
        len(molab.workspace.__all__) == 80
    )  # golden refreshed 2026-09-27 (stale at d73805f4; surface shrank in later specs)
    for name in molab.workspace.__all__:
        assert getattr(molab.workspace, name, None) is not None, name

    # ── no workspace entity answers a knowledge verb ─────────────────────────
    for cls in (molab.workspace.Project, molab.workspace.Experiment, molab.workspace.Run):
        for verb in (
            "add_knowledge",
            "knowledge",
            "set_knowledge",
            "del_knowledge",
            "has_knowledge",
            "knowledges",
            "harvest",
        ):
            assert not hasattr(cls, verb), f"{cls.__name__}.{verb}"

    # ── the knowledge side still owns the whole vocabulary ───────────────────
    for name in (
        "Knowledge",
        "Note",
        "Literature",
        "Report",
        "Finding",
        "Plan",
        "Observation",
        "KnowledgeNotFoundError",
    ):
        assert getattr(molab.knowledge, name, None) is not None, name

    # ── a workspace still materializes, and the run lands by its params ──────
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "lab"
        workspace = molab.workspace.Workspace(root=root, name="Lab")
        workspace.materialize()
        run = workspace.add_project("p").add_experiment("e").add_run(params={"seed": 42})

        assert Path(str(run.resolve())).name == "seed=42"
        assert (Path(str(run.resolve())) / "run.json").is_file()
        assert workspace.validate().ok is True


if __name__ == "__main__":
    main()
    print("knowledge-crossref-08-sever-writes: ok")
