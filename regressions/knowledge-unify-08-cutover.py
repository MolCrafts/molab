"""Goldens for knowledge-unify-08-cutover."""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge import (
    Finding,
    Knowledge,
    Literature,
    Note,
    Observation,
    Plan,
    Report,
    SourceRef,
)
from molab.knowledge.naming import knowledge_filename


def main() -> None:
    for name in (
        "Knowledge",
        "Note",
        "Literature",
        "Report",
        "Finding",
        "Plan",
        "Observation",
        "KnowledgeNotFoundError",
    ):
        assert name in __import__("molab.knowledge", fromlist=["__all__"]).__all__
    pub = __import__("molab.knowledge", fromlist=["__all__"]).__all__
    assert "Bundle" not in pub
    assert "ReferenceConcept" not in pub

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        note = Note(root / "idea")
        note.write("# x\n")
        lit = Literature(root / "paper")
        from molab.knowledge import ReferenceMeta

        lit.write(ReferenceMeta(title="T"))
        finding = Finding(root / "f", sources=[SourceRef(kind="run", ref="r")])
        finding.write()
        report = Report(root / "r", sources=[SourceRef(kind="run", ref="r")])
        report.write()
        assert (note.path / "note.json").is_file()
        assert (lit.path / "literature.json").is_file()
        assert (finding.path / "finding.json").is_file()
        assert (report.path / "report.json").is_file()
        for item in (note, lit, finding, report):
            assert not (item.path / "meta.json").exists()
        assert knowledge_filename(Note) == "note.json"
        assert knowledge_filename(Plan) == "plan.json"
        assert knowledge_filename(Observation) == "observation.json"
        names = {type(x).__name__ for x in Knowledge(root).walk()}
        assert names == {"Note", "Literature", "Finding", "Report"}


if __name__ == "__main__":
    main()
