"""Public-API goldens for knowledge-crossref-07-cli.

Hard-coded: the projected knowledge row for a seeded Note **file**
(``knowledges/cooling-rate.md``) as ``molab context`` reports it, and the
``molab runs harvest`` product as a Finding **file**
(``knowledges/finding-<run id>.md``) holding the narrative as written — with the
same-named ``finding.json`` and the same-named directory both absent (D17: a
Knowledge document is a file). The workspace is in-process
(``Workspace(...).materialize()`` + the CLI's own commands) — no third-party
runtime, no network.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from molab.cli import app
from molab.cli.workspace import resources
from molab.knowledge import Note, write_knowledge
from molab.services.knowledge_context import context_with_knowledge
from molab.workspace import Workspace
from molab.workspace.run import Run

_COOLING_RATE_ROW = (
    "projects/p/experiments/e/knowledges/cooling-rate.md",
    "Note",
    "Cooling rate",
    "cooling-rate",
)
_NARRATIVE = "Quenched at 100 K/ps; the fit held."


def _seed(ws: Workspace) -> tuple[Workspace, Run]:
    ws.materialize()
    experiment = ws.add_project("p").add_experiment("e")
    write_knowledge(
        experiment,
        name="cooling-rate",
        of=Note,
        sources=[],
        created_by="cli",
        text="# Cooling rate\n\nQuenched at 100 K/ps.\n",
    )
    run = experiment.add_run(params={"x": 1}, id="aabbccdd")
    with run.start() as ctx:
        ctx.mark_failed("oom")
    return ws, run


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        ws, run = _seed(Workspace(root=Path(raw) / "lab", name="Lab"))
        root = str(ws.root)

        projection = context_with_knowledge(ws).knowledge
        assert [(ref.path, ref.type, ref.title, ref.id) for ref in projection] == [
            _COOLING_RATE_ROW
        ], projection

        runner = CliRunner()
        context = runner.invoke(app, ["context", "--workspace", root])
        assert context.exit_code == 0, context.output
        assert "knowledge:   1" in context.stdout

        harvest = runner.invoke(
            resources.run_app,
            ["harvest", "p", "e", run.id, _NARRATIVE, "--of", "Finding", "--workspace", root],
        )
        assert harvest.exit_code == 0, harvest.output

        landed = Path(root) / "projects/p/experiments/e/knowledges" / f"finding-{run.id}.md"
        assert landed.is_file(), sorted(p.name for p in landed.parent.iterdir())
        assert _NARRATIVE in landed.read_text(encoding="utf-8")
        assert not landed.with_suffix(".json").exists()
        assert not landed.with_suffix("").is_dir()


if __name__ == "__main__":
    main()
