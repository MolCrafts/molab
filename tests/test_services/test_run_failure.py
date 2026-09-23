"""Unit tests for :mod:`molab.services.run_failure` (close-loop-02, knowledge-crossref-04).

``analyze_run_failure`` harvests through ``molab.knowledge.harvest_run`` — the
knowledge side owns execution→knowledge — so the binding itself is asserted
(``is``), and the behaviour is checked on the real path: a ``Report`` file at
``knowledges/failure-analysis-<run.id>.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.services import run_failure
from molab.services.run_failure import analyze_run_failure, build_failure_narrative
from molab.workspace import Workspace


def _run(tmp_path: Path, *, run_id: str = "aabbccdd"):
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    return ws, exp, exp.add_run(params={"x": 1}, id=run_id)


def _failed_run(tmp_path: Path, *, run_id: str = "aabbccdd", error: str = "boom"):
    ws, exp, run = _run(tmp_path, run_id=run_id)
    with run.start() as ctx:
        (ctx.execution_dir / "error.txt").write_text(error + "\n", encoding="utf-8")
        ctx.mark_failed(error)
    return ws, exp, run


class TestAnalyzeRunFailure:
    def test_writes_report_with_sources(self, tmp_path: Path) -> None:
        from molab.knowledge import Report

        _ws, _exp, run = _failed_run(tmp_path, error="unique-oom-marker")
        item = analyze_run_failure(run, created_by="test")
        assert type(item) is Report
        assert any(s.kind == "run" and s.ref == run.id for s in item.sources)
        assert "unique-oom-marker" in item.read()
        assert item.name == f"failure-analysis-{run.id}"
        # D17: a Knowledge document is a file — knowledges/<name>.md, no directory.
        assert item.path.name == f"failure-analysis-{run.id}.md"
        assert item.path.is_file()

    def test_harvest_run_binding_is_knowledge(self) -> None:
        """The redirect's contract: the module binds knowledge's own function object."""
        from molab.knowledge import Report as KnowledgeReport
        from molab.knowledge.harvest import harvest_run as knowledge_harvest_run

        assert run_failure.harvest_run is knowledge_harvest_run
        assert run_failure.Report is KnowledgeReport

    def test_idempotent_name(self, tmp_path: Path) -> None:
        _ws, _exp, run = _failed_run(tmp_path)
        a = analyze_run_failure(run, created_by="test")
        b = analyze_run_failure(run, created_by="test", narrative="updated narrative body")
        assert a.name == b.name
        assert "updated narrative body" in b.read()

    def test_refuses_non_failed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[object, ...]] = []
        monkeypatch.setattr(run_failure, "harvest_run", lambda *args: calls.append(args))
        _ws, _exp, run = _run(tmp_path)
        with run.start() as ctx:
            ctx.mark_succeeded()
        with pytest.raises(ValueError, match="succeeded"):
            analyze_run_failure(run, created_by="test")
        assert calls == [], "the status gate must refuse before any harvest call"

    def test_deterministic_narrative_no_llm(self, tmp_path: Path) -> None:
        _ws, _exp, run = _failed_run(tmp_path, error="segfault")
        text = build_failure_narrative(run)
        assert "segfault" in text
        assert run.id in text
        assert text.strip()

    def test_docstrings_name_knowledge_surface(self) -> None:
        module_doc = run_failure.__doc__ or ""
        fn_doc = analyze_run_failure.__doc__ or ""
        for doc in (module_doc, fn_doc):
            assert "molab.knowledge" in doc
            assert "molab.workspace.knowledge" not in doc
            assert "run.harvest" not in doc
