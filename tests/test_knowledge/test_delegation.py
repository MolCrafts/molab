"""Delegation: a supervised, resumable work record stored as knowledge."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge import Delegation, DelegationRecord
from molab.knowledge.concepts import _product
from molab.knowledge.delegation import DELEGATION_ACTIONS, parse_delegation
from molab.knowledge.knowledge_item import SourceRef
from molab.knowledge.record import (
    RecordConflictError,
    digest_of,
    has_record,
    record_of,
    replace_record,
)
from molab.knowledge.validate import known_classes
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace


def _record(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "goal": "Find whether sequence order changes conductivity",
        "scope": "molab:project/p1",
        "actions": ["read", "create_run", "start_execution"],
        "budget": {"worker_usd": 5.0, "executions": 4},
    }
    return {**base, **over}


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    workspace = Workspace(tmp_path / "ws", name="lab")
    workspace.materialize()
    return workspace


def _write(ws: Workspace, record: dict[str, object]) -> Delegation:
    project = ws.add_project("p")
    return write_knowledge(  # ty: ignore[invalid-return-type]
        project,
        name="Sequence study",
        of=Delegation,
        sources=[SourceRef.of(project)],
        created_by="tack",
        text="# Sequence study\n",
        record=record,
    )


class TestDelegationRecord:
    def test_defaults_are_a_fresh_open_research_delegation(self) -> None:
        record = parse_delegation(_record())
        assert record.kind == "research"
        assert record.state == "open"
        assert record.spent.executions == 0
        assert record.waits == () and record.attempts == ()

    def test_unknown_action_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalid Delegation record"):
            parse_delegation(_record(actions=["read", "rm_rf"]))

    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            DelegationRecord.model_validate({**_record(), "mystery": 1})

    def test_repeated_wait_ids_are_rejected(self) -> None:
        wait = {"id": "w1", "target": "molab:experiment/e/run/r"}
        with pytest.raises(ValueError, match="wait ids repeat"):
            parse_delegation(_record(waits=[wait, wait]))

    def test_common_keys_are_ignored(self) -> None:
        record = parse_delegation({**_record(), "class": "Delegation", "tags": ["x"]})
        assert record.goal.startswith("Find")

    def test_action_set_is_closed(self) -> None:
        assert "delegate_worker" in DELEGATION_ACTIONS
        assert "start_execution" in DELEGATION_ACTIONS


class TestDelegationDocument:
    def test_is_a_known_class(self) -> None:
        assert "Delegation" in known_classes()
        assert _product("Delegation") is Delegation

    def test_write_and_read_back(self, ws: Workspace) -> None:
        doc = _write(ws, _record())
        assert Path(str(doc.path)).name == "sequence-study.md"
        reopened = Delegation(doc.path)
        assert reopened.record().goal.startswith("Find")  # ty: ignore[unresolved-attribute]
        assert reopened.sources, "the bound scope is the source edge"

    def test_create_requires_goal_and_scope(self, ws: Workspace) -> None:
        with pytest.raises(ValueError, match="goal and its scope"):
            _write(ws, {"actions": ["read"]})

    def test_create_rejects_invalid_record(self, ws: Workspace) -> None:
        with pytest.raises(ValueError, match="invalid Delegation record"):
            _write(ws, _record(state="sleeping"))

    def test_create_rejects_planning_fields(self, ws: Workspace) -> None:
        with pytest.raises(ValueError, match="does not store"):
            _write(ws, _record(items=[]))

    def test_partial_rewrite_is_validated_against_stored_record(self, ws: Workspace) -> None:
        doc = _write(ws, _record())
        project = ws.add_project("p")
        write_knowledge(
            project,
            name="Sequence study",
            of=Delegation,
            sources=[SourceRef.of(project)],
            created_by="tack",
            text="",
            record={"state": "waiting"},
        )
        assert Delegation(doc.path).record().state == "waiting"  # ty: ignore[unresolved-attribute]
        with pytest.raises(ValueError):
            write_knowledge(
                project,
                name="Sequence study",
                of=Delegation,
                sources=[SourceRef.of(project)],
                created_by="tack",
                text="",
                record={"state": "sleeping"},
            )


class TestReplaceRecord:
    def test_replace_drops_omitted_keys_and_keeps_common_ones(self, ws: Workspace) -> None:
        doc = _write(ws, _record(acceptance=["n >= 3 seeds"]))
        before = digest_of(doc)
        new = {k: v for k, v in _record(state="waiting").items() if k != "budget"}
        after = replace_record(doc, new, if_match=before)
        assert after != before
        stored = record_of(doc)
        assert stored["state"] == "waiting"
        assert "acceptance" not in stored and "budget" not in stored
        front = doc.frontmatter()
        assert front["class"] == "Delegation" and front["created_by"] == "tack"
        assert doc.read().startswith("# Sequence study")

    def test_stale_digest_is_a_conflict(self, ws: Workspace) -> None:
        doc = _write(ws, _record())
        with pytest.raises(RecordConflictError):
            replace_record(doc, _record(), if_match="0" * 64)

    def test_invalid_record_writes_nothing(self, ws: Workspace) -> None:
        doc = _write(ws, _record())
        before = digest_of(doc)
        with pytest.raises(ValueError):
            replace_record(doc, _record(state="sleeping"))
        assert digest_of(doc) == before

    def test_body_is_replaced_in_the_same_write(self, ws: Workspace) -> None:
        doc = _write(ws, _record())
        replace_record(doc, _record(), body="## Status\n\nwaiting on e01\n")
        assert doc.read().startswith("## Status")

    def test_note_has_no_record(self, ws: Workspace) -> None:
        from molab.knowledge import Note

        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        note.write("# idea\n")
        assert not has_record(note)
        with pytest.raises(TypeError):
            replace_record(note, {"x": 1})


class TestMilestoneRecord:
    def test_a_milestone_status_is_part_of_its_record(self, ws: Workspace) -> None:
        from molab.knowledge import Milestone, Plan

        project = ws.add_project("p")
        plan = write_knowledge(
            project,
            name="Plan",
            of=Plan,
            sources=[SourceRef.of(project)],
            created_by="t",
            text="# P",
        )
        milestone = write_knowledge(
            project,
            name="Done",
            of=Milestone,
            sources=[SourceRef.of(project)],
            created_by="t",
            text="",
            cite=[(plan, "derived_from")],
            record={"stage": "s1", "criterion": "c", "status": "open"},
        )
        assert record_of(milestone)["status"] == "open"
        replace_record(milestone, {"stage": "s1", "criterion": "c", "status": "met"})
        assert milestone.frontmatter()["status"] == "met"
        assert record_of(milestone)["status"] == "met"


class TestDelegationLifecycleFields:
    def test_blocked_with_questions_amendments_and_writes(self) -> None:
        record = parse_delegation(
            _record(
                state="blocked",
                questions=["Q1: the h-type bridge connectivity?"],
                amendments=[
                    {
                        "at": "2026-11-03T16:00:00Z",
                        "by": "roykid",
                        "reason": "two runs were lost to a broken worker",
                        "changes": {"budget": {"worker_runs": 10}},
                    }
                ],
                writes=[{"key": "abc", "path": "knowledges/decision.md"}],
            )
        )
        assert record.state == "blocked"
        assert record.questions == ("Q1: the h-type bridge connectivity?",)
        assert record.amendments[0].by == "roykid"
        assert record.writes[0].path == "knowledges/decision.md"

    def test_an_amendment_needs_a_reason(self) -> None:
        with pytest.raises(ValueError):
            parse_delegation(_record(amendments=[{"at": "t", "by": "me", "reason": ""}]))


_DIGEST = "a" * 64


class TestDelegationWorkerLinks:
    """An attempt links its brief and report; the record keeps answers and the last decision."""

    def _linked(self) -> dict[str, object]:
        return _record(
            attempts=[
                {
                    "id": "a1",
                    "worker": "claude-code",
                    "task": "build the trimer",
                    "status": "done",
                    "brief": "projects/p/knowledges/brief-r1.md",
                    "brief_digest": _DIGEST,
                    "report": "projects/p/knowledges/round-1-report.md",
                    "tokens": {"input": 1200, "output": 340},
                },
                {"id": "a2", "worker": "subagent", "tokens": "unavailable"},
            ],
            decisions=[
                {
                    "at": "2026-11-05T12:00:00Z",
                    "name": "round 2",
                    "kind": "continue",
                    "reason": "round 1 passed its checks",
                    "evidence": ["molab:asset/01a1ac09-072e-7f27-9d1e-3c964b52c345"],
                    "next": "Dispatch round 2 with seed 42.",
                }
            ],
            answers=[
                {
                    "path": "projects/p/knowledges/answer-1.md",
                    "by": "roykid",
                    "text": "Mirror pairs: join 6 to 5 at every bridge.",
                }
            ],
        )

    def test_new_fields_round_trip_through_a_document(self, ws: Workspace) -> None:
        doc = _write(ws, self._linked())
        record = Delegation(doc.path).record()  # ty: ignore[unresolved-attribute]
        first, second = record.attempts
        assert first.brief == "projects/p/knowledges/brief-r1.md"
        assert first.brief_digest == _DIGEST
        assert first.report == "projects/p/knowledges/round-1-report.md"
        assert first.tokens != "unavailable" and first.tokens.input == 1200
        assert first.tokens.cache_read is None
        assert second.tokens == "unavailable"
        assert [item.kind for item in record.decisions] == ["continue"]
        assert record.answers[0].by == "roykid"
        stored = record_of(doc)
        assert stored["decisions"][0]["next"] == "Dispatch round 2 with seed 42."
        assert stored["attempts"][0]["tokens"] == {"input": 1200, "output": 340}

    def test_a_record_without_the_new_fields_still_loads(self) -> None:
        record = parse_delegation(
            _record(attempts=[{"id": "a1", "worker": "claude-code", "cost_usd": 0.5}])
        )
        attempt = record.attempts[0]
        assert attempt.brief is None and attempt.brief_digest is None
        assert attempt.report is None and attempt.tokens is None
        assert record.decisions == () and record.answers == ()

    def test_the_new_fields_are_validated(self) -> None:
        with pytest.raises(ValueError, match="brief_digest"):
            parse_delegation(
                _record(attempts=[{"id": "a1", "worker": "w", "brief_digest": "short"}])
            )
        with pytest.raises(ValueError, match="tokens"):
            parse_delegation(_record(attempts=[{"id": "a1", "worker": "w", "tokens": "none"}]))
        with pytest.raises(ValueError, match="decisions"):
            parse_delegation(_record(decisions=[{"kind": "continue"}]))
        with pytest.raises(ValueError, match="answers"):
            parse_delegation(_record(answers=[{"path": "a.md", "by": "me"}]))

    def test_the_delegation_kind_survives_the_write(self, ws: Workspace) -> None:
        doc = _write(ws, _record(kind="capability"))
        assert record_of(doc)["kind"] == "capability"
        assert Delegation(doc.path).record().kind == "capability"  # ty: ignore[unresolved-attribute]


class TestDelegationApprovals:
    """``approvals`` keep what a person approved at each human gate."""

    def _approved(self) -> dict[str, object]:
        return _record(
            approvals=[
                {
                    "gate": "plan",
                    "target": "projects/p/knowledges/plan.md",
                    "by": "roykid",
                    "at": "2026-11-04T10:00:00+00:00",
                    "note": "Go ahead with the three-rate sweep.",
                },
                {
                    "gate": "dry_run",
                    "target": "molab:experiment/01HZ",
                    "by": "roykid",
                    "at": "2026-11-04T10:05:00+00:00",
                },
            ]
        )

    def test_approvals_round_trip_through_a_document(self, ws: Workspace) -> None:
        doc = _write(ws, self._approved())
        record = Delegation(doc.path).record()  # ty: ignore[unresolved-attribute]
        plan, dry_run = record.approvals
        assert plan.gate == "plan" and plan.note == "Go ahead with the three-rate sweep."
        assert dry_run.gate == "dry_run" and dry_run.note is None
        assert dry_run.target == "molab:experiment/01HZ"
        stored = record_of(doc)
        assert stored["approvals"][1] == {
            "gate": "dry_run",
            "target": "molab:experiment/01HZ",
            "by": "roykid",
            "at": "2026-11-04T10:05:00+00:00",
        }

    def test_a_record_without_approvals_still_loads(self) -> None:
        assert parse_delegation(_record()).approvals == ()

    def test_an_approval_is_validated(self) -> None:
        with pytest.raises(ValueError, match="approvals"):
            parse_delegation(
                _record(approvals=[{"gate": "merge", "target": "x", "by": "me", "at": "t"}])
            )
        with pytest.raises(ValueError, match="approvals"):
            parse_delegation(_record(approvals=[{"gate": "plan", "target": "x", "at": "t"}]))
        with pytest.raises(ValueError, match="approvals"):
            parse_delegation(
                _record(approvals=[{"gate": "plan", "target": "", "by": "me", "at": "t"}])
            )
