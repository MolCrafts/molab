"""``molab knowledge evaluate``: a Milestone's status, measured from registered files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from molab.cli.knowledge_cmd import knowledge_app
from molab.knowledge import Milestone
from molab.knowledge.knowledge_item import SourceRef
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace

DOC = "projects/p/knowledges/dry-ffv.md"


@pytest.fixture
def lab(tmp_path: Path) -> Workspace:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    project = workspace.add_project("p")
    project.add_experiment("e")
    write_knowledge(
        project,
        name="dry ffv",
        of=Milestone,
        sources=[SourceRef.of(project)],
        created_by="intake",
        text="The dry box.\n",
        fields={
            "criterion": "FFV of the dry box",
            "checks": [{"id": "ffv", "span": "/ffv", "expected": 0.29, "tolerance": 0.01}],
        },
    )
    return workspace


def _asset(lab: Workspace, value: float) -> Any:
    run = lab.get_project("p").get_experiment("e").add_run(params={"seed": 1})
    with run.start() as ctx:
        return ctx.register({"ffv": value}, title="metrics")


def _evaluate(lab: Workspace, *args: str) -> Any:
    return CliRunner().invoke(
        knowledge_app, ["evaluate", DOC, *args, "--path", str(lab.root), "--json"]
    )


class TestEvaluate:
    def test_a_measured_check_sets_the_status(self, lab: Workspace) -> None:
        asset = _asset(lab, 0.288)

        result = _evaluate(lab, "--measure", f"ffv={asset.ref}")

        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["status"] == "met"
        assert report["measurements"] == [
            {
                "check": "ffv",
                "ref": asset.ref,
                "digest": asset.content.digest,
                "value": 0.288,
                "passed": True,
            }
        ]
        assert Milestone(Path(str(lab.root)) / DOC).fields().status == "met"

    def test_a_missed_milestone_still_exits_zero(self, lab: Workspace) -> None:
        asset = _asset(lab, 0.5)
        result = _evaluate(lab, "--measure", f"ffv={asset.ref}")
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["status"] == "missed"

    @pytest.mark.parametrize(
        ("measure", "message"),
        [
            ("ffv", "CHECK=molab:asset/<id>"),
            ("density=molab:asset/01a1c48a-536f-74fc-a9f4-b066c7bc66e1", "declares no check"),
            ("ffv=molab:asset/01a1c48a-536f-74fc-a9f4-b066c7bc66e1", "names no asset"),
        ],
    )
    def test_a_measure_that_cannot_be_read_exits_one(
        self, lab: Workspace, measure: str, message: str
    ) -> None:
        result = CliRunner().invoke(
            knowledge_app, ["evaluate", DOC, "--measure", measure, "--path", str(lab.root)]
        )
        assert result.exit_code == 1
        assert message in result.output.replace("\n", " ")
        assert Milestone(Path(str(lab.root)) / DOC).fields().status == "open"

    def test_a_document_that_is_not_a_milestone_exits_one(self, lab: Workspace) -> None:
        from molab.knowledge import Note

        write_knowledge(lab.get_project("p"), name="aside", of=Note, created_by="t", text="x\n")
        result = CliRunner().invoke(
            knowledge_app,
            [
                "evaluate",
                "projects/p/knowledges/aside.md",
                "--measure",
                "ffv=molab:asset/01a1c48a-536f-74fc-a9f4-b066c7bc66e1",
                "--path",
                str(lab.root),
            ],
        )
        assert result.exit_code == 1
        assert "not a Milestone" in result.output


class TestEvaluateRefusals:
    def test_one_check_given_two_sources_is_refused(self, lab: Workspace) -> None:
        asset = _asset(lab, 0.288)
        result = _evaluate(lab, "--measure", f"ffv={asset.ref}", "--measure", f"ffv={asset.ref}")
        assert result.exit_code == 1
        assert "two sources" in result.output

    def test_a_status_typed_by_hand_is_measured_over(self, lab: Workspace) -> None:
        asset = _asset(lab, 0.5)
        path = Path(str(lab.root)) / DOC
        text = path.read_text(encoding="utf-8").replace("checks:", "status: met\nchecks:", 1)
        path.write_text(text, encoding="utf-8")

        result = _evaluate(lab, "--measure", f"ffv={asset.ref}")

        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["status"] == "missed"
