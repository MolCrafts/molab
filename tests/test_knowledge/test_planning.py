"""Plan, Roadmap, Todo, and Milestone stay on their own fields."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge import (
    Milestone,
    Plan,
    Roadmap,
    SourceRef,
    Todo,
    campaign_of,
    check_campaign,
)
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace


def _lab(tmp_path: Path):
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    return ws


def _overview(ws: Workspace) -> Plan:
    return write_knowledge(
        ws,
        name="PBIX overview",
        of=Plan,
        sources=[SourceRef(kind="file", ref=str(tmp_brief(ws)))],
        created_by="test",
        text="How crosslinking changes free volume.\n",
    )


def tmp_brief(ws: Workspace) -> Path:
    path = Path(str(ws.root)) / "brief.pdf"
    path.write_text("brief", encoding="utf-8")
    return path


class TestPlanningRoles:
    def test_a_plan_refuses_stages(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        with pytest.raises(ValueError, match="does not store"):
            write_knowledge(
                ws,
                name="PBIX overview",
                of=Plan,
                sources=[SourceRef(kind="file", ref="brief.pdf")],
                created_by="test",
                text="overview\n",
                record={"stages": []},
            )

    def test_campaign_links_the_four_documents(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        plan = _overview(ws)
        write_knowledge(
            ws,
            name="PBIX roadmap",
            of=Roadmap,
            sources=[SourceRef.of(plan)],
            created_by="test",
            text="Order of the campaign.\n",
            record={
                "stages": [
                    {"id": "monomers", "title": "Fragments", "experiment": "monomers"},
                    {
                        "id": "equilibrate",
                        "title": "Boxes",
                        "experiment": "stage1-equilibrate",
                        "depends_on": ["monomers"],
                    },
                ]
            },
        )
        write_knowledge(
            ws,
            name="PBIX todos",
            of=Todo,
            sources=[SourceRef.of(plan)],
            created_by="test",
            text="Open work.\n",
            record={
                "items": [
                    {
                        "id": "draw",
                        "title": "Draw the fragments",
                        "stage": "monomers",
                        "status": "open",
                    }
                ]
            },
        )
        write_knowledge(
            ws,
            name="Fragments shown",
            of=Milestone,
            sources=[SourceRef.of(plan)],
            created_by="test",
            text="The pictures are the evidence.\n",
            record={
                "stage": "monomers",
                "criterion": "Seven fragments are assets and shown in molvis",
            },
        )

        campaign = campaign_of(plan)
        check_campaign(campaign)

        assert plan.planning_role() == "overview"
        assert plan.planning_fields() == {}
        assert len(campaign.roadmaps) == 1
        assert campaign.roadmaps[0].planning_role() == "roadmap"
        assert [stage.id for stage in campaign.roadmaps[0].stages()] == [
            "monomers",
            "equilibrate",
        ]
        assert campaign.todos[0].items()[0].stage == "monomers"
        assert campaign.milestones[0].stage() == "monomers"
        assert campaign.milestones[0].status() == "open"
        assert "items" not in campaign.milestones[0].planning_fields()

    def test_a_milestone_cannot_close_an_unknown_stage(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        plan = _overview(ws)
        write_knowledge(
            ws,
            name="PBIX roadmap",
            of=Roadmap,
            sources=[SourceRef.of(plan)],
            created_by="test",
            text="Order.\n",
            record={"stages": [{"id": "monomers", "title": "Fragments"}]},
        )
        write_knowledge(
            ws,
            name="Too early",
            of=Milestone,
            sources=[SourceRef.of(plan)],
            created_by="test",
            text="No.\n",
            record={"stage": "missing", "criterion": "does not exist"},
        )

        with pytest.raises(ValueError, match="missing"):
            check_campaign(campaign_of(plan))

    def test_a_roadmap_on_another_host_is_part_of_the_campaign(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        plan = _overview(ws)
        project = ws.add_project("poly")
        write_knowledge(
            project,
            name="Stages",
            of=Roadmap,
            sources=[SourceRef.of(plan)],
            created_by="test",
            text="Order.\n",
            record={"stages": [{"id": "monomers", "title": "Fragments"}]},
        )

        assert [stage.id for stage in campaign_of(plan).roadmaps[0].stages()] == ["monomers"]

    def test_a_milestone_status_must_stay_legal(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        plan = _overview(ws)
        milestone = write_knowledge(
            ws,
            name="Shown",
            of=Milestone,
            sources=[SourceRef.of(plan)],
            created_by="test",
            text="Evidence.\n",
            record={"stage": "monomers", "criterion": "The pictures exist"},
        )

        with pytest.raises(ValueError, match="status"):
            milestone.write(status="nope")
        assert milestone.status() == "open"

    def test_a_roadmap_cycle_is_refused(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        with pytest.raises(ValueError, match="cycle"):
            write_knowledge(
                ws,
                name="PBIX roadmap",
                of=Roadmap,
                sources=[SourceRef(kind="file", ref="brief.pdf")],
                created_by="test",
                text="Order.\n",
                record={
                    "stages": [
                        {"id": "a", "title": "A", "depends_on": ["b"]},
                        {"id": "b", "title": "B", "depends_on": ["a"]},
                    ]
                },
            )
