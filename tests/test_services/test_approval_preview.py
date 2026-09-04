"""Plan approval-gate preview — ReviewPack builders + markdown projection.

``services.plan_runtime.preview`` renders the shared gate-time review text
consumed identically by the CLI interactive approver and the server's approvals
inbox (Python = UI).
"""

from __future__ import annotations

from pathlib import Path

from molexp.harness.store.file_artifact_store import FileArtifactStore
from molexp.services.plan_runtime.preview import (
    build_review_pack,
    render_approval_preview,
    render_review_pack,
)
from molexp.workspace import Workspace


def _seeded_run(tmp_path: Path, artifacts: dict[str, dict]):
    """One run + one sealed execution carrying the given ``kind`` → obj artifacts."""
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    run = ws.add_project("p").add_experiment("e").add_run(id="r1")
    execution = run.start()
    execution.__enter__()
    store = FileArtifactStore.for_execution(execution)
    for kind, obj in artifacts.items():
        store.put_json(kind, obj, created_by="test", parent_ids=[])
    exec_id = execution.id
    execution.__exit__(None, None, None)
    return run, exec_id


class TestRenderApprovalPreview:
    def test_spec_intent_renders_the_gated_fields(self, tmp_path: Path) -> None:
        run, exec_id = _seeded_run(
            tmp_path,
            {
                "experiment_spec": {
                    "title": "LJ minima",
                    "objective": "tabulate r_min",
                    "variables": [{"name": "sigma", "value": {"value": [0.9, 1.0]}, "unit": ""}],
                    "resolved_questions": [{"question": "grid?", "answer": "0.001"}],
                },
            },
        )
        text = render_approval_preview(run, exec_id, "experiment_spec")
        assert "LJ minima" in text
        assert "tabulate r_min" in text
        assert "sigma = [0.9, 1.0]" in text
        assert "grid? -> 0.001" in text

    def test_plan_intent_includes_source_and_verdicts(self, tmp_path: Path) -> None:
        run, exec_id = _seeded_run(
            tmp_path,
            {
                "workflow_source": {"source": "def build_workflow():\n    return None\n"},
                "test_result": {"status": "passed"},
            },
        )
        text = render_approval_preview(run, exec_id, "final_report")
        assert "def build_workflow():" in text
        assert "generated tests    : passed" in text
        assert "compiled / dry-ran : False" in text

    def test_missing_artifacts_render_a_stated_absence(self, tmp_path: Path) -> None:
        run, exec_id = _seeded_run(tmp_path, {})
        text = render_approval_preview(run, exec_id, "experiment_spec")
        assert text
        assert "no experiment_spec" in text or "empty" in text.lower() or "spec" in text.lower()


class TestBuildReviewPack:
    def test_returns_a_pack_matching_the_rendered_preview(self, tmp_path: Path) -> None:
        run, exec_id = _seeded_run(
            tmp_path,
            {"experiment_spec": {"title": "T", "objective": "O"}},
        )
        pack = build_review_pack(run, exec_id, "experiment_spec")
        assert pack.step_id == "draft_spec"
        assert "approve" in pack.decision_options
        assert render_review_pack(pack) == render_approval_preview(run, exec_id, "experiment_spec")
