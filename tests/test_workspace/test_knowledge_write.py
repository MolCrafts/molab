"""``write_knowledge`` — sourced Knowledge writer."""

from __future__ import annotations

from typing import Any

from molab.workspace import Finding, Knowledge, SourceRef


class TestWriteKnowledge:
    def test_creates_entity_json_and_body(self, experiment: Any) -> None:
        item = Finding.write(
            experiment,
            name="finding-demo",
            sources=[SourceRef(kind="experiment", ref=experiment.id)],
            created_by="tester",
            body="# Finding\n\nhello\n",
            title="demo",
        )
        assert isinstance(item, Finding)
        assert item.metadata.created_by == "tester"
        assert item.body().startswith("# Finding")
        assert not (item.resolve() / "meta.json").exists()

    def test_repeat_write_is_idempotent(self, experiment: Any) -> None:
        kwargs = {
            "name": "finding-demo",
            "sources": [SourceRef(kind="experiment", ref=experiment.id)],
            "created_by": "tester",
            "body": "first\n",
        }
        Finding.write(experiment, **kwargs)
        Finding.write(experiment, **{**kwargs, "body": "second\n"})
        assert "second" in experiment.get_folder("finding-demo", cls=Knowledge).body()
