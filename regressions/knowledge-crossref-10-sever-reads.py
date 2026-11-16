"""Public-API goldens for knowledge-crossref-10-sever-reads.

Hard-coded: the workspace's read paths no longer know knowledge. A raw
``assemble_workspace_context`` returns ``knowledge == []`` (by design — the one
producer is ``molab.services``), the layout validator accepts a ``knowledges/``
tree with a headless child and a plain file item (the container-head check is
gone), the ``bundle_index`` re-export shim is deleted, and the cache prefetch
helper is named for the ``meta.json`` Concept mounts it serves. Uses
``molab.workspace`` only — no third-party runtime.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import molab.workspace
from molab.workspace import fs_cached
from molab.workspace.validate import validate_workspace
from molab.workspace.workspace_context import WorkspaceContext, assemble_workspace_context


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "lab"
        workspace = molab.workspace.Workspace(root=root, name="Lab")
        workspace.materialize()
        project = workspace.add_project("alpha")
        experiment = project.add_experiment("sweep")
        experiment.add_run(params={"seed": 1})

        # ── the raw assembler projects no knowledge, on any tree ─────────────
        context = assemble_workspace_context(workspace)
        assert isinstance(context, WorkspaceContext)
        assert not hasattr(context, "knowledge")
        assert "open_questions" not in context.model_dump()
        assert "knowledge" not in context.model_dump()

        # ── a headless knowledges/ child and a file item are never flagged ───
        knowledges = root / "knowledges"
        (knowledges / "loose").mkdir(parents=True, exist_ok=True)
        (knowledges / "lab-note.md").write_text("# lab note\n", encoding="utf-8")

        report = validate_workspace(root)
        assert report.ok is True, report.violations
        rules = {v.rule for v in report.violations}
        assert "layout.container" not in rules
        assert "layout.stray" not in rules

    # ── the re-export shim is gone for real ──────────────────────────────────
    assert importlib.util.find_spec("molab.workspace.bundle_index") is None

    # ── the prefetch helper is renamed, not deleted ──────────────────────────
    assert not hasattr(fs_cached, "_prefetch_knowledge_children")
    assert "_KNOWLEDGE_SKIP_DEFAULT" not in vars(fs_cached)
    assert hasattr(fs_cached, "_prefetch_meta_mounts")
    assert hasattr(fs_cached, "_meta_mount_skip")
    assert not hasattr(fs_cached, "_META_MOUNT_SKIP")


if __name__ == "__main__":
    main()
    print("knowledge-crossref-10-sever-reads: ok")
