"""``write_knowledge`` — sourced Knowledge writer."""

from __future__ import annotations

from typing import Any

from molab.workspace import Finding, SourceRef
from molab.workspace.folder import Folder
from molab.workspace.knowledge_write import write_knowledge


class TestWriteKnowledge:
    def test_creates_entity_json_and_body(self, experiment: Any) -> None:
        item = write_knowledge(
            experiment,
            name="finding-demo",
            of=Finding,
            sources=[SourceRef(kind="experiment", ref=experiment.id)],
            created_by="tester",
            text="# Finding\n\nhello\n",
            title="demo",
        )
        assert isinstance(item, Finding)
        assert not isinstance(item, Folder)
        assert item.read().startswith("# Finding")
        assert (item.path / "finding.json").is_file()
        assert not (item.path / "meta.json").exists()

    def test_repeat_write_is_idempotent(self, experiment: Any) -> None:
        kwargs = {
            "name": "finding-demo",
            "of": Finding,
            "sources": [SourceRef(kind="experiment", ref=experiment.id)],
            "created_by": "tester",
            "text": "first\n",
        }
        write_knowledge(experiment, **kwargs)
        write_knowledge(experiment, **{**kwargs, "text": "second\n"})
        assert "second" in experiment.knowledge("finding-demo").read()
