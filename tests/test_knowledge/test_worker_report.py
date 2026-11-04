"""Worker records: a ``worker_report`` on a Report, a ``brief`` on a Note."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from molab.cli import app
from molab.cli.knowledge_cmd import knowledge_app
from molab.knowledge import Note, Report, SourceRef
from molab.knowledge.record import record_of
from molab.knowledge.validate import validate_knowledge
from molab.knowledge.worker_report import (
    WORKER_RECORD_CLASSES,
    BriefRecord,
    WorkerReportRecord,
    check_worker_record,
    parse_brief,
    parse_worker_report,
)
from molab.knowledge.write import write_knowledge

DIGEST = hashlib.sha256(b"the brief").hexdigest()


def _report(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "worker_report",
        "delegation": "projects/p/knowledges/pbix-study.md",
        "attempt": "a1",
        "brief": "projects/p/knowledges/brief-r1.md",
        "brief_digest": DIGEST,
        "outcome": "done",
        "summary": "Built the trimer and the 10-mer.",
        "checks": {
            "trimer_atoms": {"verdict": "pass", "value": 205},
            "bridge_sites": {"verdict": "pass", "value": "6<->5", "note": "both ends"},
            "decamer_atoms": {"verdict": "unknown"},
        },
        "products": [{"path": "projects/p/experiments/e/scratch/trimer.pdb", "kind": "structure"}],
        "files_changed": ["projects/p/experiments/e/workflow.py"],
        "workflow": "projects/p/experiments/e/workflow.py",
        "protocol_deviations": [{"item": "seed", "expected": "42", "actual": "7"}],
        "capability_gaps": [
            {
                "component": "molpy",
                "title": "no port-aware join",
                "repro": "mp.join(a, b, ports=...)",
                "version": "0.4.1",
            }
        ],
        "open_questions": ["Is the CF3 bridge chiral?"],
        "next": "Run the 10-mer through MMFF.",
        "tokens": {"input": 1200, "output": 340, "reasoning": 80},
    }
    return {**base, **over}


def _brief(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "brief",
        "delegation": "projects/p/knowledges/pbix-study.md",
        "round": 1,
        "digest": DIGEST,
        "inputs": ["projects/p/knowledges/plan.md"],
        "protocol": {"reproduce": "molab:execution/e20", "seed": 42, "charges": "neutral"},
    }
    return {**base, **over}


class TestWorkerReportRecord:
    def test_a_full_record_parses(self) -> None:
        record = parse_worker_report(_report())
        assert record.outcome == "done"
        assert record.checks["trimer_atoms"].value == 205
        assert record.checks["bridge_sites"].value == "6<->5"
        assert record.products[0].kind == "structure"
        assert record.capability_gaps[0].component == "molpy"
        assert record.tokens != "unavailable" and record.tokens.reasoning == 80

    def test_what_is_not_said_defaults_to_empty(self) -> None:
        minimal = {
            key: value
            for key, value in _report().items()
            if key
            in {"kind", "delegation", "attempt", "brief", "brief_digest", "outcome", "summary"}
        }
        record = parse_worker_report(minimal)
        assert record.checks == {} and record.products == ()
        assert record.protocol_deviations == () and record.capability_gaps == ()
        assert record.files_changed == () and record.open_questions == ()
        assert record.tokens == "unavailable" and record.next is None

    def test_a_bad_verdict_names_the_check(self) -> None:
        bad = _report(checks={"atoms": {"verdict": "maybe"}})
        with pytest.raises(ValueError, match=r"checks\.atoms\.verdict"):
            parse_worker_report(bad)

    def test_an_unknown_field_is_named(self) -> None:
        with pytest.raises(ValueError, match="mystery"):
            parse_worker_report(_report(mystery=1))
        with pytest.raises(ValueError, match=r"products\.0\.size"):
            parse_worker_report(_report(products=[{"path": "p", "kind": "k", "size": 3}]))

    def test_outcome_component_and_digest_are_closed(self) -> None:
        with pytest.raises(ValueError, match="outcome"):
            parse_worker_report(_report(outcome="finished"))
        with pytest.raises(ValueError, match=r"capability_gaps\.0\.component"):
            parse_worker_report(
                _report(capability_gaps=[{"component": "rdkit", "title": "t", "repro": "r"}])
            )
        with pytest.raises(ValueError, match="brief_digest"):
            parse_worker_report(_report(brief_digest="not-a-digest"))

    def test_the_kind_is_fixed(self) -> None:
        with pytest.raises(ValueError, match="kind"):
            WorkerReportRecord.model_validate(_report(kind="report"))

    def test_common_keys_are_ignored(self) -> None:
        record = parse_worker_report({**_report(), "class": "Report", "created_by": "w"})
        assert record.attempt == "a1"


class TestBriefRecord:
    def test_a_brief_parses(self) -> None:
        record = parse_brief(_brief())
        assert record.round == 1
        assert record.protocol.seed == 42 and record.protocol.realization is None
        assert record.inputs == ("projects/p/knowledges/plan.md",)

    def test_round_starts_at_one_and_digest_is_sha256(self) -> None:
        with pytest.raises(ValueError, match="round"):
            parse_brief(_brief(round=0))
        with pytest.raises(ValueError, match="digest"):
            parse_brief(_brief(digest="abc"))

    def test_protocol_is_closed(self) -> None:
        with pytest.raises(ValueError, match=r"protocol\.realization"):
            parse_brief(_brief(protocol={"realization": "replica"}))
        with pytest.raises(ValueError, match=r"protocol\.temperature"):
            parse_brief(_brief(protocol={"temperature": 300}))

    def test_the_protocol_is_required(self) -> None:
        with pytest.raises(ValueError, match="protocol"):
            BriefRecord.model_validate({k: v for k, v in _brief().items() if k != "protocol"})


class TestCheckWorkerRecord:
    def test_each_kind_has_one_class(self) -> None:
        assert dict(WORKER_RECORD_CLASSES) == {"worker_report": "Report", "brief": "Note"}

    def test_a_report_on_a_note_and_a_brief_on_a_report_are_refused(self) -> None:
        with pytest.raises(
            ValueError, match="worker_report record belongs on a Report, not a Note"
        ):
            check_worker_record(Note, _report(), existing=None)
        with pytest.raises(ValueError, match="brief record belongs on a Note, not a Report"):
            check_worker_record(Report, _brief(), existing=None)

    def test_other_kinds_and_no_record_are_left_alone(self) -> None:
        check_worker_record(Report, None, existing=None)
        check_worker_record(Note, {"kind": "research", "goal": "g"}, existing=None)
        check_worker_record(Report, {"tags": ["x"]}, existing=None)

    def test_a_rewrite_is_validated_over_the_stored_record(self) -> None:
        stored = {**_report(), "class": "Report", "name": "r", "created_by": "w"}
        check_worker_record(Report, {"outcome": "partial"}, existing=stored)
        check_worker_record(Report, None, existing=stored)
        check_worker_record(Report, {"tags": ["late"]}, existing=stored)
        with pytest.raises(ValueError, match="outcome"):
            check_worker_record(Report, {"outcome": "nearly"}, existing=stored)
        with pytest.raises(ValueError, match="belongs on a Report"):
            check_worker_record(Note, {"summary": "s"}, existing=stored)


def _project(lab: Any) -> Any:
    return lab.get_project("p")


def _write_report(lab: Any, record: dict[str, object], *, name: str = "Round 1 report") -> Report:
    project = _project(lab)
    return write_knowledge(  # ty: ignore[invalid-return-type]
        project,
        name=name,
        of=Report,
        sources=[SourceRef.of(project)],
        created_by="worker",
        text="# Round 1\n\nBuilt both chains.\n",
        record=record,
    )


def _write_brief(lab: Any, record: dict[str, object]) -> Note:
    return write_knowledge(  # ty: ignore[invalid-return-type]
        _project(lab),
        name="Brief r1",
        of=Note,
        created_by="tack",
        text="the brief",
        record=record,
    )


def _issues(lab: Any) -> list[tuple[str, str]]:
    return [
        (i["rule"], i["path"])
        for i in validate_knowledge(lab, errors_only=False)
        if i["rule"] != "knowledge.section_drift"
    ]


class TestWorkerDocuments:
    def test_a_worker_report_round_trips_through_a_report(self, lab: Any) -> None:
        doc = _write_report(lab, _report())
        stored = record_of(doc)
        assert stored == _report()
        assert parse_worker_report(stored).checks["trimer_atoms"].value == 205
        assert doc.frontmatter()["created_by"] == "worker"

    def test_a_brief_round_trips_through_a_note(self, lab: Any) -> None:
        doc = _write_brief(lab, _brief())
        assert record_of(doc) == _brief()
        assert parse_brief(record_of(doc)).digest == DIGEST

    def test_the_wrong_class_is_refused_before_anything_is_written(self, lab: Any) -> None:
        with pytest.raises(ValueError, match="brief record belongs on a Note"):
            _write_report(lab, _brief(), name="Not a brief")
        with pytest.raises(ValueError, match="worker_report record belongs on a Report"):
            _write_brief(lab, _report())
        knowledges = Path(str(_project(lab).resolve())) / "knowledges"
        assert not (knowledges / "not-a-brief.md").exists()
        assert not (knowledges / "brief-r1.md").exists()

    def test_an_invalid_record_is_refused_with_the_field_named(self, lab: Any) -> None:
        with pytest.raises(ValueError, match=r"checks\.atoms\.verdict"):
            _write_report(lab, _report(checks={"atoms": {"verdict": "maybe"}}))
        with pytest.raises(ValueError, match="extra"):
            _write_report(lab, _report(extra="field"))

    def test_a_partial_rewrite_merges_over_the_stored_record(self, lab: Any) -> None:
        doc = _write_report(lab, _report())
        _write_report(lab, {"outcome": "partial", "next": "Retry with seed 42."})
        after = parse_worker_report(record_of(doc))
        assert after.outcome == "partial" and after.next == "Retry with seed 42."
        assert after.checks["trimer_atoms"].value == 205
        with pytest.raises(ValueError, match="outcome"):
            _write_report(lab, {"outcome": "nearly"})

    def test_valid_worker_documents_conform(self, lab: Any) -> None:
        _write_brief(lab, _brief())
        _write_report(lab, _report())
        assert _issues(lab) == []
        result = CliRunner().invoke(app, ["validate", "-ws", str(lab.root)])
        assert result.exit_code == 0, result.output
        assert "conforms" in result.output

    def test_a_hand_written_invalid_record_is_reported(self, lab: Any) -> None:
        folder = Path(str(_project(lab).resolve())) / "knowledges"
        folder.mkdir(exist_ok=True)
        (folder / "bad.md").write_text(
            "---\nclass: Report\nname: Bad\nkind: worker_report\nattempt: a1\n---\n# Bad\n",
            encoding="utf-8",
        )
        (folder / "misplaced.md").write_text(
            "---\nclass: Note\nname: Misplaced\nkind: worker_report\n---\n# Misplaced\n",
            encoding="utf-8",
        )
        found = _issues(lab)
        assert ("knowledge.record", "projects/p/knowledges/bad.md") in found
        assert ("knowledge.record", "projects/p/knowledges/misplaced.md") in found


class TestKnowledgeWriteCli:
    def test_write_report_with_a_worker_report_record(self, lab: Any) -> None:
        brief = _write_brief(lab, _brief())
        root = str(lab.root)
        result = CliRunner().invoke(
            knowledge_app,
            [
                "write", "Round 1 report", "Built both chains.",
                "--on", "projects/p",
                "--class", "Report",
                "--source", str(brief.path),
                "--record", json.dumps(_report()),
                "--created-by", "worker",
                "--path", root,
            ],
        )  # fmt: skip
        assert result.exit_code == 0, result.output
        doc = Report(Path(root) / "projects" / "p" / "knowledges" / "round-1-report")
        assert record_of(doc) == _report()
        assert doc.frontmatter()["created_by"] == "worker"
        assert "brief-r1.md" in doc.read()

    def test_an_invalid_record_fails_with_the_field_named(self, lab: Any) -> None:
        brief = _write_brief(lab, _brief())
        bad = _report(checks={"atoms": {"verdict": "maybe"}})
        result = CliRunner().invoke(
            knowledge_app,
            [
                "write", "Round 1 report", "Built both chains.",
                "--on", "projects/p",
                "--class", "Report",
                "--source", str(brief.path),
                "--record", json.dumps(bad),
                "--path", str(lab.root),
            ],
        )  # fmt: skip
        assert result.exit_code == 1
        assert "checks.atoms.verdict" in result.output
        assert not (Path(str(lab.root)) / "projects/p/knowledges/round-1-report.md").exists()

    def test_a_brief_on_a_report_fails(self, lab: Any) -> None:
        result = CliRunner().invoke(
            knowledge_app,
            [
                "write", "Brief", "the brief",
                "--on", "projects/p",
                "--class", "Report",
                "--source", "10.1000/xyz",
                "--record", json.dumps(_brief()),
                "--path", str(lab.root),
            ],
        )  # fmt: skip
        assert result.exit_code == 1
        assert "belongs on a Note, not a Report" in result.output
