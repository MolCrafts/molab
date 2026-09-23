"""Public-API goldens for knowledge-unify-02-workspace."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from molab.knowledge import Finding as KnowledgeFinding
from molab.workspace import Finding, Folder, SourceRef, Workspace
from molab.workspace.folder import concept_from_dir
from molab.workspace.knowledge import Report
from molab.workspace.knowledge_write import write_knowledge


def main() -> None:
    assert Finding is KnowledgeFinding
    from molab.knowledge import Report as KnowledgeReport

    assert Report is KnowledgeReport
    with tempfile.TemporaryDirectory() as raw:
        ws = Workspace(root=Path(raw) / "lab", name="Lab")
        ws.materialize()
        exp = ws.add_project("p").add_experiment("e")
        item = write_knowledge(
            exp,
            name="tg-rise",
            of=Finding,
            sources=[SourceRef(kind="experiment", ref=exp.id)],
            created_by="tester",
            text="# Finding\n\nmobility rises\n",
        )
        dest = Path(exp.resolve()) / "knowledges" / "tg-rise"
        assert (dest / "finding.json").is_file()
        assert (dest / "index.md").is_file()
        assert not (dest / "meta.json").exists()
        payload = json.loads((dest / "finding.json").read_text())
        assert "type" not in payload
        assert "kind" not in payload
        assert type(item) is Finding
        assert not isinstance(item, Folder)
        try:
            concept_from_dir(dest, exp)
        except TypeError:
            pass
        else:
            raise AssertionError("concept_from_dir should skip knowledge dirs")


if __name__ == "__main__":
    main()
