"""Unit tests for molab.workspace.refs."""

from __future__ import annotations

import inspect

import pydantic
import pytest

import molab.workspace
from molab.workspace import Experiment, Project, Workspace
from molab.workspace.refs import (
    REF_SCHEME,
    AmbiguousRefError,
    InvalidRefError,
    MolabRef,
    RefNotFoundError,
    is_ref,
    parse_ref,
    qualify_run_id,
    ref_of,
)

_FIVE_GOLDENS: tuple[tuple[str, MolabRef], ...] = (
    ("molab:project/P", MolabRef(project_id="P")),
    ("molab:experiment/E", MolabRef(experiment_id="E")),
    ("molab:experiment/E/run/r1", MolabRef(experiment_id="E", run_id="r1")),
    (
        "molab:experiment/E/run/r1/execution/e01",
        MolabRef(experiment_id="E", run_id="r1", execution_id="e01"),
    ),
    (
        "molab:experiment/E/run/r1/artifact/A",
        MolabRef(experiment_id="E", run_id="r1", artifact_id="A"),
    ),
)


class TestIsRef:
    def test_scheme_is_molab_prefix(self) -> None:
        assert REF_SCHEME == "molab:"

    def test_prefix_matches_experiment_and_garbage(self) -> None:
        assert is_ref("molab:experiment/E") is True
        assert is_ref("molab:garbage") is True

    def test_url_bare_id_and_empty_are_not_refs(self) -> None:
        assert is_ref("molab://x") is False
        assert is_ref("r1") is False
        assert is_ref("") is False

    def test_parse_ref_calls_is_ref(self) -> None:
        assert "is_ref(" in inspect.getsource(parse_ref)


class TestMolabRef:
    def test_five_shapes_report_kind(self) -> None:
        kinds = [ref.kind for _, ref in _FIVE_GOLDENS]
        assert kinds == ["project", "experiment", "run", "execution", "artifact"]

    def test_project_and_experiment_together_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MolabRef(project_id="P", experiment_id="E")

    def test_run_without_experiment_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MolabRef(run_id="r1")

    def test_execution_and_artifact_together_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MolabRef(
                experiment_id="E",
                run_id="r1",
                execution_id="e01",
                artifact_id="A",
            )

    def test_segment_containing_slash_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MolabRef(project_id="a/b")

    def test_segment_dotdot_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MolabRef(project_id="..")

    def test_str_goldens(self) -> None:
        for golden, ref in _FIVE_GOLDENS:
            assert str(ref) == golden

    def test_asset_kind(self) -> None:
        assert parse_ref("molab:asset/X").kind == "asset"

    def test_asset_excludes_every_other_segment(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MolabRef(asset_id="x", experiment_id="e")


class TestParseRef:
    @pytest.mark.parametrize(("golden", "ref"), _FIVE_GOLDENS)
    def test_round_trip(self, golden: str, ref: MolabRef) -> None:
        assert str(parse_ref(golden)) == golden
        assert parse_ref(str(ref)) == ref

    @pytest.mark.parametrize(
        "bad",
        [
            "molab://projects/x",
            "project/P",
            "molab:project/P/experiment/E",
            "molab:experiment/E/artifact/A",
            "molab:experiment/E/run/r1/",
            "molab:experiment//run/r1",
            "molab:experiment/E/run/r1/execution/e01/artifact/A",
            "molab:experiment/E/asset/X",
            "molab:asset/",
        ],
    )
    def test_invalid_ref(self, bad: str) -> None:
        with pytest.raises(InvalidRefError):
            parse_ref(bad)

    def test_kind_run_selects_run_id(self) -> None:
        parsed = parse_ref("molab:experiment/E/run/r1", kind="run")
        assert parsed.run_id == "r1"

    def test_kind_run_on_experiment_ref_rejected(self) -> None:
        with pytest.raises(InvalidRefError, match="expected a run reference"):
            parse_ref("molab:experiment/E", kind="run")

    def test_asset_round_trip(self) -> None:
        parsed = parse_ref("molab:asset/0190abc")
        assert parsed.asset_id == "0190abc"
        assert parsed.kind == "asset"
        assert str(parsed) == "molab:asset/0190abc"
        assert str(parse_ref("molab:asset/X")) == "molab:asset/X"
        assert parse_ref("molab:asset/X").kind == "asset"


class TestRefOf:
    def test_project_experiment_and_run(
        self, project: Project, experiment: Experiment, run
    ) -> None:
        assert ref_of(project) == MolabRef(project_id=project.id)
        assert ref_of(experiment) == MolabRef(experiment_id=experiment.id)
        assert str(ref_of(run)) == f"molab:experiment/{experiment.id}/run/{run.id}"

    def test_artifact_on_a_run(self, run) -> None:
        assert ref_of(run, artifact_id="A").kind == "artifact"

    def test_asset(self, experiment: Experiment, tmp_path) -> None:
        source = tmp_path / "input.txt"
        source.write_text("payload")
        asset = experiment.assets.import_asset("mydata", source)
        assert ref_of(asset).kind == "asset"
        assert str(ref_of(asset)) == f"molab:asset/{asset.id}"

    def test_foreign_object_and_artifact_on_a_project(self, project: Project) -> None:
        with pytest.raises(TypeError):
            ref_of(object())
        with pytest.raises(TypeError):
            ref_of(project, artifact_id="A")

    def test_not_exported_from_workspace_package(self) -> None:
        assert "ref_of" not in molab.workspace.__all__


class TestQualifyRunId:
    def test_unique_run_id(self, workspace: Workspace, experiment: Experiment) -> None:
        experiment.add_run(id="r1")
        ref = qualify_run_id(workspace, "r1")
        assert ref == MolabRef(experiment_id=experiment.id, run_id="r1")

    def test_same_id_in_two_experiments_is_ambiguous(
        self, workspace: Workspace, project: Project
    ) -> None:
        exp_a = project.add_experiment("Alpha")
        exp_b = project.add_experiment("Beta")
        exp_a.add_run(id="r1")
        exp_b.add_run(id="r1")
        with pytest.raises(AmbiguousRefError) as exc_info:
            qualify_run_id(workspace, "r1")
        err = exc_info.value
        assert len(err.candidates) == 2
        experiment_ids = {candidate.experiment_id for candidate in err.candidates}
        assert len(experiment_ids) == 2

    def test_missing_run_id(self, workspace: Workspace) -> None:
        with pytest.raises(RefNotFoundError) as exc_info:
            qualify_run_id(workspace, "r1")
        err = exc_info.value
        assert err.segment == "run"
        assert err.ref is None
        assert "run 'r1' not found" in str(err)

    def test_not_exported_from_workspace_package(self) -> None:
        assert "qualify_run_id" not in molab.workspace.__all__
