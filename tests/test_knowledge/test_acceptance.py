"""A Milestone's checks, and the verb that measures them.

A check is a number with its tolerance and the place it sits in a registered
file. ``evaluate_milestone`` reads that place and writes the status; a
status a person typed must still agree with the measurements beside it, and
``molab validate`` re-reads the cited bytes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from molab.knowledge import Milestone
from molab.knowledge.acceptance import AcceptanceError, evaluate_milestone, evidence_problems
from molab.knowledge.concepts import MilestoneFields
from molab.knowledge.knowledge_item import SourceRef
from molab.knowledge.validate import validate_knowledge
from molab.knowledge.write import write_knowledge
from molab.workspace.domain import ExecutionStatus
from molab.workspace.refs import ref_of

CHECK = {"id": "ffv", "span": "/ffv", "expected": 0.29, "tolerance": 0.01}


def _fields(**overrides: Any) -> dict[str, Any]:
    return {"criterion": "FFV of the dry box", "checks": [CHECK], **overrides}


def _measured(value: float, passed: bool) -> dict[str, Any]:
    return {
        "check": "ffv",
        "ref": "molab:asset/a1",
        "digest": "sha256:" + "0" * 64,
        "value": value,
        "passed": passed,
    }


def _register(run: Any, data: Any, *, title: str = "metrics") -> Any:
    """Register *data* from a succeeded attempt of *run*; the asset."""
    with run.start() as ctx:
        return ctx.register(data, title=title)


def _milestone(lab: Any, **fields: Any) -> Milestone:
    project = lab.get_project("p")
    doc = write_knowledge(
        project,
        name="dry ffv",
        of=Milestone,
        sources=[SourceRef.of(project)],
        created_by="intake",
        text="The dry box.\n",
        fields=_fields(**fields),
    )
    assert isinstance(doc, Milestone)
    return doc


def _errors(lab: Any) -> set[str]:
    return {
        issue["rule"]
        for issue in validate_knowledge(lab, errors_only=True)
        if issue["severity"] == "error"
    }


class TestCheckFields:
    def test_a_check_within_tolerance_passes(self) -> None:
        check = MilestoneFields.model_validate(_fields()).checks[0]
        assert check.passes(0.295)
        assert not check.passes(0.31)

    def test_a_relative_tolerance_scales_with_the_expected_value(self) -> None:
        fields = _fields(checks=[{**CHECK, "expected": 200.0, "tolerance": 0.05, "relative": True}])
        check = MilestoneFields.model_validate(fields).checks[0]
        assert check.passes(209.0)
        assert not check.passes(211.0)

    @pytest.mark.parametrize(
        ("compare", "value", "passed"),
        [("at_most", 0.01, True), ("at_most", 0.02, False), ("at_least", 0.02, True)],
    )
    def test_a_bound_compares_one_sided(self, compare: str, value: float, passed: bool) -> None:
        fields = _fields(checks=[{**CHECK, "expected": 0.015, "tolerance": 0, "compare": compare}])
        assert MilestoneFields.model_validate(fields).checks[0].passes(value) is passed

    @pytest.mark.parametrize(
        "fields",
        [
            _fields(checks=[CHECK, CHECK]),
            _fields(checks=[{**CHECK, "tolerance": -1}]),
            _fields(checks=[{**CHECK, "span": ""}]),
            _fields(checks=[{**CHECK, "critical": False}]),
            _fields(checks=[{**CHECK, "unit": "nm"}]),
            {"criterion": "no checks", "measurements": [_measured(0.29, True)]},
            _fields(measurements=[{**_measured(0.29, True), "check": "gone"}]),
            _fields(measurements=[_measured(0.29, True), _measured(0.29, True)]),
            _fields(measurements=[_measured(0.5, True)]),
            _fields(status="met"),
            _fields(status="met", measurements=[_measured(0.5, False)]),
            _fields(status="missed"),
            _fields(status="missed", measurements=[_measured(0.29, True)]),
        ],
    )
    def test_fields_that_do_not_hold_together_are_refused(self, fields: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            MilestoneFields.model_validate(fields)

    @pytest.mark.parametrize(
        "fields",
        [
            _fields(),
            _fields(status="met", measurements=[_measured(0.29, True)]),
            _fields(status="missed", measurements=[_measured(0.5, False)]),
            _fields(measurements=[_measured(0.29, True)]),
            {"criterion": "a shape, judged by reading", "status": "met"},
        ],
    )
    def test_fields_that_hold_together_are_accepted(self, fields: dict[str, Any]) -> None:
        MilestoneFields.model_validate(fields)


class TestEvaluate:
    def test_a_value_within_tolerance_sets_met(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        doc = _milestone(lab)

        fields = evaluate_milestone(doc, {"ffv": asset.ref})

        assert fields.status == "met"
        (measured,) = fields.measurements
        assert (measured.check, measured.value, measured.passed) == ("ffv", 0.288, True)
        assert measured.ref == asset.ref
        assert measured.digest == asset.content.digest
        assert Milestone(doc.path).fields() == fields

    def test_a_value_outside_tolerance_sets_missed(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.35})
        assert evaluate_milestone(_milestone(lab), {"ffv": asset.ref}).status == "missed"

    def test_a_failed_optional_check_does_not_miss(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288, "drift": 0.5})
        optional = {
            "id": "drift",
            "span": "/drift",
            "expected": 0.01,
            "tolerance": 0,
            "compare": "at_most",
            "critical": False,
        }
        doc = _milestone(lab, checks=[CHECK, optional])

        fields = evaluate_milestone(doc, {"ffv": asset.ref, "drift": asset.ref})

        assert fields.status == "met"
        assert [item.passed for item in fields.measurements] == [True, False]

    def test_an_unmeasured_critical_check_leaves_it_open(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        second = {**CHECK, "id": "ffv-wet", "span": "/ffv_wet"}
        doc = _milestone(lab, checks=[CHECK, second])
        assert evaluate_milestone(doc, {"ffv": asset.ref}).status == "open"

    def test_the_evaluation_keeps_the_narrative_and_cites_the_asset(
        self, lab: Any, run: Any
    ) -> None:
        asset = _register(run, {"ffv": 0.288})
        doc = _milestone(lab)
        evaluate_milestone(doc, {"ffv": asset.ref})
        body = Milestone(doc.path).read()
        assert "The dry box." in body
        assert f"({asset.ref}#/ffv)" in body

    def test_a_second_evaluation_replaces_the_first(self, lab: Any, experiment: Any) -> None:
        first = _register(experiment.add_run(params={"seed": 1}), {"ffv": 0.35})
        second = _register(experiment.add_run(params={"seed": 2}), {"ffv": 0.288})
        doc = _milestone(lab)
        evaluate_milestone(doc, {"ffv": first.ref})

        fields = evaluate_milestone(doc, {"ffv": second.ref})

        assert fields.status == "met"
        assert [item.ref for item in fields.measurements] == [second.ref]

    @pytest.mark.parametrize(
        ("data", "match"),
        [({"other": 1.0}, "not in the asset"), ({"ffv": "high"}, "not a number")],
    )
    def test_a_point_that_is_not_a_number_is_refused(
        self, lab: Any, run: Any, data: Any, match: str
    ) -> None:
        asset = _register(run, data)
        with pytest.raises(AcceptanceError, match=match):
            evaluate_milestone(_milestone(lab), {"ffv": asset.ref})

    def test_an_unknown_check_is_refused(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        with pytest.raises(AcceptanceError, match="declares no check 'density'"):
            evaluate_milestone(_milestone(lab), {"density": asset.ref})

    def test_a_milestone_without_checks_is_refused(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        doc = _milestone(lab, checks=[])
        with pytest.raises(AcceptanceError, match="declares no checks"):
            evaluate_milestone(doc, {"ffv": asset.ref})

    def test_a_source_that_is_not_an_asset_is_refused(self, lab: Any, run: Any) -> None:
        _register(run, {"ffv": 0.288})
        with pytest.raises(AcceptanceError, match="not an asset reference"):
            evaluate_milestone(_milestone(lab), {"ffv": str(ref_of(run))})

    def test_an_imported_file_is_refused(self, lab: Any, tmp_path: Path) -> None:
        source = tmp_path / "typed.json"
        source.write_text('{"ffv": 0.29}', encoding="utf-8")
        asset = lab.get_project("p").import_asset("typed", source)
        with pytest.raises(AcceptanceError, match="no attempt produced"):
            evaluate_milestone(_milestone(lab), {"ffv": asset.ref})

    def test_a_failed_attempts_file_is_refused(self, lab: Any, run: Any) -> None:
        with run.start() as ctx:
            asset = ctx.register({"ffv": 0.29}, title="metrics")
            ctx.mark_failed("diverged")
        with pytest.raises(AcceptanceError, match="failed"):
            evaluate_milestone(_milestone(lab), {"ffv": asset.ref})

    def test_an_adopted_attempts_file_is_refused(
        self, lab: Any, experiment: Any, run: Any, tmp_path: Path
    ) -> None:
        from datetime import UTC, datetime

        from molab.workspace.domain import ExecutionOrigin
        from molab.workspace.history import SYSTEM_AGENT

        log = tmp_path / "job.log"
        log.write_text("done\n", encoding="utf-8")
        result = tmp_path / "result.json"
        result.write_text('{"ffv": 0.29}', encoding="utf-8")
        now = datetime.now(UTC)
        attempt = run.adopt_execution(
            status=ExecutionStatus.SUCCEEDED, started_at=now, finished_at=now, log=str(log)
        )
        asset = experiment.assets.register(
            result,
            title="result",
            created_by=SYSTEM_AGENT,
            origin=ExecutionOrigin(
                project_id=experiment.project.id,
                experiment_id=experiment.id,
                run_id=run.id,
                execution_id=attempt.id,
            ),
        )
        with pytest.raises(AcceptanceError, match="molab did not run"):
            evaluate_milestone(_milestone(lab), {"ffv": asset.ref})


class TestValidateEvidence:
    def test_an_evaluated_milestone_is_clean(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        evaluate_milestone(_milestone(lab), {"ffv": asset.ref})
        assert _errors(lab) == set()

    def test_a_typed_measurement_that_names_no_asset_is_reported(self, lab: Any) -> None:
        _milestone(lab, status="met", measurements=[_measured(0.29, True)])
        assert _errors(lab) == {"knowledge.milestone_evidence"}

    def test_a_measurement_whose_bytes_changed_is_reported(
        self, lab: Any, run: Any, tmp_path: Path
    ) -> None:
        asset = _register(run, {"ffv": 0.288})
        evaluate_milestone(_milestone(lab), {"ffv": asset.ref})
        replacement = tmp_path / "new.json"
        replacement.write_text('{"ffv": 0.5}', encoding="utf-8")
        lab.assets_at(asset.scope).replace_bytes(asset.id, replacement)

        assert _errors(lab) == {"knowledge.milestone_evidence"}

    def test_a_measurement_that_records_other_bytes_is_reported(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        typed = {**_measured(0.288, True), "ref": asset.ref}
        doc = _milestone(lab, status="met", measurements=[typed])

        assert evidence_problems(doc) == [f"check 'ffv': {asset.ref} changed since it was measured"]

    def test_a_measurement_that_records_another_value_is_reported(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        typed = {**_measured(0.285, True), "ref": asset.ref, "digest": asset.content.digest}
        doc = _milestone(lab, status="met", measurements=[typed])

        assert evidence_problems(doc) == [
            f"check 'ffv': records 0.285, but {asset.ref} holds 0.288"
        ]


class TestCheckArithmetic:
    @pytest.mark.parametrize(
        ("expected", "tolerance", "relative", "value"),
        [(0.3, 0.1, False, 0.4), (1.1, 0.1, False, 1.0), (0.3, 0.1, True, 0.33)],
    )
    def test_a_value_on_the_bound_passes(
        self, expected: float, tolerance: float, relative: bool, value: float
    ) -> None:
        check = {**CHECK, "expected": expected, "tolerance": tolerance, "relative": relative}
        assert MilestoneFields.model_validate(_fields(checks=[check])).checks[0].passes(value)

    def test_a_value_past_the_bound_fails(self) -> None:
        check = {**CHECK, "expected": 0.3, "tolerance": 0.1}
        assert not MilestoneFields.model_validate(_fields(checks=[check])).checks[0].passes(0.4001)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    @pytest.mark.parametrize("compare", ["within", "at_most", "at_least"])
    def test_a_value_that_is_not_finite_never_passes(self, compare: str, value: float) -> None:
        check = {**CHECK, "compare": compare}
        assert not MilestoneFields.model_validate(_fields(checks=[check])).checks[0].passes(value)

    @pytest.mark.parametrize(
        "check",
        [
            {**CHECK, "expected": float("nan")},
            {**CHECK, "tolerance": float("inf")},
            {**CHECK, "expected": 0, "tolerance": 0.05, "relative": True},
        ],
    )
    def test_a_check_with_no_usable_bound_is_refused(self, check: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            MilestoneFields.model_validate(_fields(checks=[check]))


class TestWhoseBytes:
    """The gate is on the bytes: a run's own, produced by molab, and not swapped since."""

    def test_replaced_bytes_are_refused(self, lab: Any, run: Any, tmp_path: Path) -> None:
        asset = _register(run, {"ffv": 0.9})
        typed = tmp_path / "typed.json"
        typed.write_text('{"ffv": 0.29}', encoding="utf-8")
        lab.assets_at(asset.scope).replace_bytes(asset.id, typed)

        with pytest.raises(AcceptanceError, match="asset replace"):
            evaluate_milestone(_milestone(lab), {"ffv": asset.ref})

    def test_bytes_the_run_registers_again_are_its_own_again(
        self, lab: Any, run: Any, tmp_path: Path
    ) -> None:
        from molab.workspace.domain import ExecutionMode

        asset = _register(run, {"ffv": 0.9})
        typed = tmp_path / "typed.json"
        typed.write_text('{"ffv": 0.29}', encoding="utf-8")
        lab.assets_at(asset.scope).replace_bytes(asset.id, typed)
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            again = ctx.register({"ffv": 0.288}, title="metrics")

        assert evaluate_milestone(_milestone(lab), {"ffv": again.ref}).status == "met"

    def test_a_resumed_run_keeps_what_the_failed_attempt_registered(
        self, lab: Any, run: Any
    ) -> None:
        from molab.workspace.domain import ExecutionMode

        with run.start() as ctx:
            asset = ctx.register({"ffv": 0.288}, title="metrics")
            ctx.mark_failed("node lost")
        with run.start(mode=ExecutionMode.RESUME):
            pass

        assert evaluate_milestone(_milestone(lab), {"ffv": asset.ref}).status == "met"

    def test_a_failed_rerun_that_registers_the_same_bytes_leaves_the_evidence(
        self, lab: Any, run: Any
    ) -> None:
        from molab.workspace.domain import ExecutionMode

        asset = _register(run, {"ffv": 0.288})
        evaluate_milestone(_milestone(lab), {"ffv": asset.ref})
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            ctx.register({"ffv": 0.288}, title="metrics")
            ctx.mark_failed("node lost")

        assert _errors(lab) == set()

    @pytest.mark.parametrize(
        "text", ['{"ffv": NaN}', '{"ffv": Infinity}', '{"ffv": 1' + "0" * 400 + "}"]
    )
    def test_a_number_that_is_not_finite_is_refused(
        self, lab: Any, run: Any, tmp_path: Path, text: str
    ) -> None:
        source = tmp_path / "metrics.json"
        source.write_text(text, encoding="utf-8")
        with run.start() as ctx:
            asset = ctx.register(source, title="metrics")
        with pytest.raises(AcceptanceError, match="not a finite number"):
            evaluate_milestone(_milestone(lab), {"ffv": asset.ref})

    def test_bytes_that_are_gone_are_reported_not_raised(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.288})
        evaluate_milestone(_milestone(lab), {"ffv": asset.ref})
        Path(lab.assets_at(asset.scope).payload_path(asset.id)).unlink()

        assert _errors(lab) == {"knowledge.milestone_evidence"}

    def test_a_store_that_cannot_be_searched_is_reported_not_raised(
        self, lab: Any, run: Any
    ) -> None:
        asset = _register(run, {"ffv": 0.288})
        evaluate_milestone(_milestone(lab), {"ffv": asset.ref})
        legacy = Path(str(lab.root)) / "projects" / "p" / "assets" / "old"
        (legacy / "versions").mkdir(parents=True)
        (legacy / "asset.json").write_text("{}", encoding="utf-8")

        assert _errors(lab) == {"knowledge.milestone_evidence"}


class TestEvaluateWrites:
    def test_a_status_typed_by_hand_is_replaced(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"ffv": 0.35})
        doc = _milestone(lab)
        path = Path(str(doc.path))
        path.write_text(
            path.read_text(encoding="utf-8").replace("checks:", "status: met\nchecks:", 1),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="disagrees"):
            Milestone(doc.path).fields()

        assert evaluate_milestone(Milestone(doc.path), {"ffv": asset.ref}).status == "missed"
        assert Milestone(doc.path).fields().status == "missed"

    def test_a_document_that_changed_meanwhile_is_not_overwritten(
        self, lab: Any, run: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.knowledge import acceptance
        from molab.knowledge.fields import DigestConflictError, replace_fields

        asset = _register(run, {"ffv": 0.288})
        doc = _milestone(lab)
        measure = acceptance._measure

        def tightened(*args: Any) -> Any:
            found = measure(*args)
            replace_fields(doc, _fields(checks=[{**CHECK, "tolerance": 0.0001}]))
            return found

        monkeypatch.setattr(acceptance, "_measure", tightened)

        with pytest.raises(DigestConflictError):
            evaluate_milestone(doc, {"ffv": asset.ref})
        assert Milestone(doc.path).fields().status == "open"

    def test_an_html_milestone_keeps_its_links_inside_a_markdown_block(
        self, lab: Any, run: Any
    ) -> None:
        asset = _register(run, {"ffv": 0.288})
        project = lab.get_project("p")
        doc = write_knowledge(
            project,
            name="dry ffv page",
            of=Milestone,
            sources=[SourceRef.of(project)],
            created_by="intake",
            text="<p>The dry box.</p>\n",
            fields=_fields(),
            format="html",
        )
        assert isinstance(doc, Milestone)

        evaluate_milestone(doc, {"ffv": asset.ref})

        body = Milestone(doc.path).read()
        link = body.index(f"({asset.ref}#/ffv)")
        assert body.rindex("<molab-markdown>", 0, link) > body.rfind("</molab-markdown>", 0, link)
        assert _errors(lab) == set()

    def test_a_span_a_link_cannot_carry_cites_the_asset_alone(self, lab: Any, run: Any) -> None:
        asset = _register(run, {"Tg (K)": 412.0})
        check = {"id": "tg", "span": "/Tg (K)", "expected": 410.0, "tolerance": 5.0}
        doc = _milestone(lab, checks=[check])

        assert evaluate_milestone(doc, {"tg": asset.ref}).status == "met"
        assert f"({asset.ref})" in Milestone(doc.path).read()
        assert _errors(lab) == set()
