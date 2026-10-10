"""Public-API goldens for knowledge-crossref-03-verbs.

Hard-coded: the ``cites`` edge role on a Knowledge → Knowledge citation, a
bare-path cite that must survive (the branch a resolver would ``TypeError`` on
and drop), the ``body=""`` remount that keeps its body, the harvested body
carrying ``succeeded`` and the result ``0.42``, the two ``ValueError``
preconditions, and ``parse_knowledge_class("Finding") is Finding``. Uses
``molab.workspace``'s public surface plus the new ``molab.knowledge`` verbs —
no third-party runtime.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from molab.knowledge import Finding, Knowledge, Observation, SourceRef, parse_class
from molab.knowledge.write import mount_note, write_knowledge
from molab.workspace import Workspace
from molab.workspace.refs import ref_of


def _refuses(call: Callable[[], object]) -> bool:
    """Whether calling *call* raises ``ValueError`` — a refusal, not a fallback."""
    try:
        call()
    except ValueError:
        return True
    return False


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        workspace = Workspace(root=Path(raw) / "lab", name="Lab")
        workspace.materialize()
        experiment = workspace.add_project("p").add_experiment("e")
        knowledges = Path(str(experiment.resolve())) / "knowledges"

        # The class-name entry point lives on the knowledge side and returns the
        # very class object a caller imports.
        assert parse_class("Finding") is Finding

        # A Knowledge -> Knowledge citation rides the typed edge, role `cites`.
        # The experiment source is a molab reference, written once as derived_from.
        background = mount_note(experiment, "Background", body="# Background\n")
        finding = write_knowledge(
            experiment,
            name="Finding One",
            of=Finding,
            sources=[SourceRef.of(experiment)],
            created_by="tester",
            text="# Finding\n\nmobility rises\n",
            cite=[(background, "cites")],
        )
        assert finding.path == knowledges / "finding-one.md"
        assert [(e.target, e.role) for e in finding.links()] == [
            (str(ref_of(experiment)), "derived_from"),
            (str(background.path), "cites"),
        ]

        # A bare path is linked verbatim -- never through the embed resolver,
        # which would raise on it and lose the edge silently.
        outside = Path(raw) / "outside-family"
        outside.mkdir()
        second = write_knowledge(
            experiment,
            name="Finding Two",
            of=Finding,
            sources=[SourceRef(kind="file", ref="raw.txt")],
            created_by="tester",
            text="# Finding\n",
            cite=[(str(outside), "references")],
        )
        second_edges = [(e.target, e.role) for e in second.links()]
        assert (str(outside), "references") in second_edges
        assert any(
            target.endswith("raw.txt") and role == "derived_from" for target, role in second_edges
        )

        # The mount is idempotent on the slug and keeps its body -- including a
        # repeat that passes an empty body -- and an empty-body mount still
        # materializes the document.
        kept = mount_note(experiment, "My Idea", body="# Kept\n")
        again = mount_note(experiment, "my-idea", body="")
        empty = mount_note(experiment, "Empty One")
        assert again.path == kept.path
        assert again.read() == "# Kept\n"
        assert empty.exists() and empty.read() == ""

        # A terminal run harvests into a sourced document under its experiment;
        # a non-terminal run and a blank narrative are refused, never degraded.
        run = experiment.add_run(params={"temperature": 350})
        assert _refuses(
            lambda: Observation.harvest(run, narrative="too early", created_by="tester")
        )
        with run.start():
            pass
        assert _refuses(lambda: Observation.harvest(run, narrative="   \n", created_by="t"))

        harvested = Observation.harvest(
            run,
            narrative="Mobility rises with temperature.",
            created_by="tester",
            results={"mobility": 0.42},
        )
        body = harvested.read()
        assert run.id in harvested.name
        assert harvested.path == knowledges / f"{harvested.name}.md"
        assert "succeeded" in body
        assert "0.42" in body
        assert "Mobility rises with temperature." in body
        reopened = Knowledge.open(harvested.path)
        assert isinstance(reopened, Observation)
        assert [(s.kind, s.ref) for s in reopened.sources] == [
            ("run", str(ref_of(run))),
            ("experiment", str(ref_of(experiment))),
        ]


if __name__ == "__main__":
    main()
