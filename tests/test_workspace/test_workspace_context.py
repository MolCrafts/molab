"""WorkspaceContext read-model + assembler (workspace-context-01-assembler, P0.2).

References:
- spec:       ``.claude/specs/workspace-context-01-assembler.md``
- acceptance: ``.claude/specs/workspace-context-01-assembler.acceptance.md``
- design:     ``.claude/notes/integration.md`` §1
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from molab.knowledge import Note
from molab.workspace import Run, Workspace, WorkspaceContext
from molab.workspace.domain import ExecutionMode
from molab.workspace.workspace_context import (
    ContextFocus,
    assemble_workspace_context,
)


def _ws(tmp_path: Path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab", name="Lab")
    ws.materialize()
    return ws


def _tree(root_path: object) -> set[str]:
    return {str(p) for p in Path(str(root_path)).rglob("*")}


def _fail_then_retry(run: Run) -> None:
    """e01 fails, e02 (a RETRY of e01) succeeds — built through the public API."""
    with pytest.raises(RuntimeError), run.start():
        raise RuntimeError("boom")
    with run.start(mode=ExecutionMode.RETRY, predecessor="e01"):
        pass


class TestAssembleWorkspaceContext:
    def test_projects_experiments_runs_and_artifacts_assembled_and_ordered(
        self, tmp_path: Path
    ) -> None:
        ws = _ws(tmp_path)
        exp = ws.add_project("p").add_experiment("e", params={"lr": 1e-3})
        r1 = exp.add_run(params={"seed": 1})
        with r1.start() as ctx:
            ctx.emit_artifact({"loss": 0.1}, name="m1.json")
        r2 = exp.add_run(params={"seed": 2})
        with r2.start() as ctx:
            ctx.emit_artifact({"loss": 0.2}, name="m2.json")
        note = Note.mount(ws, "idea")
        note.write("# Idea\n\nnarrative\n")

        c = assemble_workspace_context(ws)

        assert [p.name for p in c.projects] == ["p"]
        assert [e.name for e in c.experiments] == ["e"]
        assert c.experiments[0].project_id == ws.get_project("p").id
        assert len(c.recent_runs) == 2
        assert len(c.artifacts) >= 2
        assert "knowledge" not in c.model_dump()
        # recent_runs ordered by finished/started descending
        ts = [(rr.finished_at or rr.started_at) for rr in c.recent_runs]
        assert ts == sorted(ts, key=lambda t: t or datetime(1970, 1, 1, tzinfo=UTC), reverse=True)

    def test_the_read_model_has_no_document_fields(self, tmp_path: Path) -> None:
        c = assemble_workspace_context(_ws(tmp_path))

        assert isinstance(c, WorkspaceContext)
        assert {"knowledge", "open_questions"}.isdisjoint(WorkspaceContext.model_fields)
        assert "knowledge" not in c.model_dump()

    def test_empty_workspace_yields_all_empty_collections(self, tmp_path: Path) -> None:
        c = assemble_workspace_context(_ws(tmp_path))
        assert c.projects == []
        assert c.experiments == []
        assert c.workflows == []
        assert c.recent_runs == []
        assert c.failed_runs == []
        assert c.running_runs == []
        assert c.artifacts == []
        assert c.stale_or_missing == []

    def test_focus_is_echoed_and_assembly_writes_nothing(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        before = _tree(ws.resolve())
        focus = ContextFocus(project_id="p", selected_object_refs=["obj-1"])
        c = assemble_workspace_context(ws, focus=focus)
        assert c.focus == focus
        assert _tree(ws.resolve()) == before  # pure read — nothing written

    def test_health_flags_cover_failed_stale_and_orphan(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        exp = ws.add_project("p").add_experiment("e")

        rf = exp.add_run(params={"k": 1})
        with rf.start() as ctx:
            ctx.emit_artifact(b"{}", name="ghost.json")
            ctx.mark_failed("simulated failure")
        record = Path(rf.execution_dir("e01")) / "execution.json"
        raw = json.loads(record.read_text(encoding="utf-8"))
        raw["artifacts"][0]["run_id"] = "ghost-run"
        record.write_text(json.dumps(raw), encoding="utf-8")

        beat = datetime(2020, 1, 1, tzinfo=UTC)
        rr = exp.add_run(params={"k": 2})
        running_ctx = rr.start()
        running_ctx.__enter__()
        alive = Path(str(rr.run_dir)) / "executions" / running_ctx.id / "alive"
        # HEARTBEAT_STALE_SECONDS == 600.0
        old = time.time() - 601.0
        os.utime(alive, (old, old))
        now = beat + timedelta(minutes=20)

        try:
            c = assemble_workspace_context(ws, now=now)
            kinds = {h.kind for h in c.stale_or_missing}
            assert "failed_run" in kinds
            assert "stale_running" in kinds
            assert "orphan_artifact" in kinds
            assert any(x.run_id == rf.id for x in c.failed_runs)
            assert any(x.run_id == rr.id for x in c.running_runs)
        finally:
            running_ctx.__exit__(None, None, None)

    def test_run_status_is_status_label(self, tmp_path: Path) -> None:
        """arch-own-02e D70: ``RunRef.status`` is ``Run.status_label``; failures stay flagged."""
        ws = _ws(tmp_path)
        run_a = ws.add_project("p").add_experiment("e").add_run(params={"k": 1})
        _fail_then_retry(run_a)

        c = ws.context()

        ref = next(r for r in c.recent_runs if r.run_id == run_a.id)
        assert ref.status == run_a.status_label
        assert ref.status == "succeeded"
        assert any(x.run_id == run_a.id for x in c.failed_runs)

    def test_queued_run_is_running_and_not_stale(self, tmp_path: Path) -> None:
        """A QUEUED attempt is active: listed as running, never flagged stale (no alive yet)."""
        ws = _ws(tmp_path)
        run_q = ws.add_project("p").add_experiment("e").add_run(params={"k": 1})
        run_q._create_execution()
        alive = Path(str(run_q.run_dir)) / "executions" / "e01" / "alive"
        assert not alive.exists()

        c = assemble_workspace_context(ws)

        assert any(x.run_id == run_q.id for x in c.running_runs)
        assert not any(h.kind == "stale_running" for h in c.stale_or_missing)

    def test_code_binding_is_a_workflow_and_unbound_is_not(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        bound = project.add_experiment("bound")
        bound.bind_workflow("code", entrypoint="train.py:build")
        bare = project.add_experiment("bare")
        ctx = assemble_workspace_context(ws)
        ids = {item.experiment_id for item in ctx.workflows}
        assert bound.id in ids
        assert bare.id not in ids


class TestArtifactRowsIgnoreNamedAssets:
    def test_emitted_ids_only_and_a_ghost_manifest_adds_nothing(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"{}", name="m.json")
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        imported = ws.assets.import_asset("greeting", source, action="copy")
        (Path(str(ws.root)) / "assets.json").write_text(
            '{"assets":[{"id":"ghost-manifest-asset"}]}',
            encoding="utf-8",
        )

        assembled = assemble_workspace_context(ws)

        assert [row.asset_id for row in assembled.artifacts] == [artifact.id]
        assert [row.execution_id for row in assembled.artifacts] == ["e01"]
        assert imported.id not in {row.asset_id for row in assembled.artifacts}
        flagged = {flag.ref for flag in assembled.stale_or_missing}
        assert "ghost-manifest-asset" not in flagged
        assert imported.id not in flagged

    def test_assembler_does_not_name_the_manifest_scanner(self) -> None:
        source = Path(assemble_workspace_context.__code__.co_filename).read_text(encoding="utf-8")
        assert "scan_assets" not in source
        assert "assets.json" not in source
