"""What ``molab init`` rewrites in the knowledge of a workspace an older molab wrote.

Each fixture is the shape of a real document from a workspace written before
the classes declared their fields: a key the class no longer declares, and the
retired ``Delegation`` class. After the migration ``molab validate`` reports
nothing for them, and no value is lost: every moved key is in the narrative.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from molab.knowledge.frontmatter import split_frontmatter
from molab.knowledge.migration import migrate_knowledge
from molab.knowledge.validate import validate_knowledge

#: Frontmatter an older molab accepted, by the class that carried it.
LEGACY: dict[str, tuple[str, dict[str, object]]] = {
    "todo-with-gaps": (
        "Todo",
        {
            "items": [{"id": "a", "title": "A", "status": "done"}],
            "gaps": [{"id": "a", "component": "molpy", "repro": "多行\n复现"}],
        },
    ),
    "finding-from-a-delegation": (
        "Finding",
        {"delegation": "projects/p/knowledges/sup.md", "holds_under": "seed=42"},
    ),
    "assessment": (
        "Report",
        {"assessment": {"verdict": "pass", "checks": ["a"]}, "delegation": "d", "target": "t"},
    ),
    "brief": (
        "Note",
        {"kind": "brief", "delegation": "d", "round": 1, "inputs": ["x.md"], "digest": "ab"},
    ),
    "plan-with-parameters": (
        "Plan",
        {"content_key": "k", "delegation": "d", "parameters": {"model": ["a", "b"]}},
    ),
    "capability-gap": (
        "Observation",
        {"capability_gap": {"component": "molab"}, "decision": "continue", "delegation": "d"},
    ),
}

ANCHOR = "- [@derived_from box](molab:asset/01a1ac09-072e-7f27-9d1e-3c964b52c345)\n"


def _write(lab: Any, name: str, meta: dict[str, object], body: str, suffix: str = ".md") -> Path:
    from molab.knowledge.frontmatter import dump_frontmatter

    folder = Path(str(lab.root)) / "knowledges"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}{suffix}"
    path.write_text(dump_frontmatter(meta, body, path=path), encoding="utf-8")
    return path


def _knowledge_errors(lab: Any) -> list[tuple[str, str]]:
    return [
        (issue["rule"], issue["path"])
        for issue in validate_knowledge(lab, errors_only=True)
        if issue["severity"] == "error"
    ]


def _moved(body: str) -> dict[str, object]:
    """The keys the migration put in the narrative's fenced YAML block."""
    block = body.split("```yaml\n", 1)[1].split("\n```", 1)[0]
    return yaml.safe_load(block)


class TestUndeclaredKeys:
    @pytest.mark.parametrize("name", sorted(LEGACY))
    def test_a_key_the_class_does_not_declare_moves_to_the_narrative(
        self, lab: Any, name: str
    ) -> None:
        from molab.knowledge.concepts import _product

        cls, fields = LEGACY[name]
        meta = {"class": cls, "name": name, "created_by": "tack", **fields}
        path = _write(lab, name, meta, f"# {name}\n\nThe text.\n{ANCHOR}")
        assert ("knowledge.fields", f"knowledges/{name}.md") in _knowledge_errors(lab)

        migrate_knowledge(lab)

        after, body = split_frontmatter(path.read_text(encoding="utf-8"), path=path)
        model = _product(cls).FIELDS
        declared = set(model.model_fields) if model is not None else set()
        kept = {key: value for key, value in fields.items() if key in declared}
        moved = {key: value for key, value in fields.items() if key not in declared}
        assert after == {"class": cls, "name": name, "created_by": "tack", **kept}
        assert body.startswith(f"# {name}\n\nThe text.\n{ANCHOR}")
        assert _moved(body) == moved
        assert _knowledge_errors(lab) == []

    def test_an_html_document_keeps_its_format(self, lab: Any) -> None:
        meta = {"class": "Finding", "name": "Box", "holds_under": "seed=42"}
        path = _write(lab, "box", meta, f"<molab-markdown>\n{ANCHOR}</molab-markdown>\n", ".html")

        migrate_knowledge(lab)

        after, body = split_frontmatter(path.read_text(encoding="utf-8"), path=path)
        assert after == {"class": "Finding", "name": "Box"}
        assert _moved(body) == {"holds_under": "seed=42"}
        assert _knowledge_errors(lab) == []

    def test_a_second_run_changes_nothing(self, lab: Any) -> None:
        cls, fields = LEGACY["finding-from-a-delegation"]
        path = _write(lab, "f", {"class": cls, "name": "F", **fields}, ANCHOR)
        migrate_knowledge(lab)
        once = path.read_text(encoding="utf-8")

        assert migrate_knowledge(lab) == []
        assert path.read_text(encoding="utf-8") == once

    def test_a_refused_value_of_a_declared_key_is_left_for_validate(self, lab: Any) -> None:
        path = _write(lab, "claim", {"class": "Hypothesis", "name": "C", "verdict": "likely"}, "")
        before = path.read_text(encoding="utf-8")

        migrate_knowledge(lab)

        assert path.read_text(encoding="utf-8") == before
        assert ("knowledge.fields", "knowledges/claim.md") in _knowledge_errors(lab)


class TestRetiredClass:
    def test_a_delegation_is_a_plan_holding_its_record_in_the_narrative(self, lab: Any) -> None:
        record = {
            "kind": "research",
            "goal": "回放五个模型",
            "scope": "molab:experiment/E1",
            "actions": ["read", "create_run"],
            "budget": {"executions": 5},
            "state": "done",
            "waits": [{"id": "w1", "target": "molab:experiment/E1/run/R1/execution/e01"}],
        }
        meta = {"class": "Delegation", "name": "Supervision", "created_by": "tack", **record}
        path = _write(lab, "supervision", meta, "# Supervision\n\n## Status\n")
        assert ("knowledge.class", "knowledges/supervision.md") in _knowledge_errors(lab)

        assert [Path(rewritten).name for rewritten in migrate_knowledge(lab)] == [path.name]

        after, body = split_frontmatter(path.read_text(encoding="utf-8"), path=path)
        assert after == {"class": "Plan", "name": "Supervision", "created_by": "tack"}
        assert _moved(body) == record
        assert _knowledge_errors(lab) == []
