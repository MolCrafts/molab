"""``molab.knowledge.write`` — the sourced writer, the note mount, source normalization.

Three behaviors are load-bearing here and each has its own guard below:

- the destination comes from :func:`molab.knowledge.location.folder` and the
  bytes land through ``Concept.write`` (one derivation, one persistence path);
- the **cite channel keeps all three branches** — a Knowledge document through
  ``.ref``, a ``Folder``/``Asset`` through the embed resolver, and a bare path
  straight to ``append_link``. The third branch must never be routed through the
  resolver: it would raise, and the edge would be silently dropped;
- ``mount_note`` materializes a document even with an empty body, and a repeat
  call (including ``body=""``) never truncates an existing body.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from molab.knowledge import Finding, Knowledge, Literature, Note, SourceRef
from molab.knowledge.location import folder
from molab.knowledge.write import mount_note, normalize_sources, write_knowledge
from molab.workspace.folder import Folder


def _write(experiment: Any, **overrides: Any) -> Knowledge:
    kwargs: dict[str, Any] = {
        "name": "finding-demo",
        "of": Finding,
        "sources": [SourceRef(kind="experiment", ref=experiment.id)],
        "created_by": "tester",
        "text": "# Finding\n\nhello\n",
    }
    kwargs.update(overrides)
    return write_knowledge(experiment, **kwargs)


class TestWriteKnowledge:
    def test_writes_the_sourced_document_at_the_derived_path(self, experiment: Any) -> None:
        item = _write(experiment, title="demo")

        assert isinstance(item, Finding)
        assert not isinstance(item, Folder)
        assert item.path == folder(experiment, "finding-demo", Finding)
        assert Path(item.path).name == "finding-demo.md"
        assert Path(item.path).parent == Path(str(experiment.resolve())) / "knowledges"
        assert item.exists()
        assert item.read().startswith("# Finding")

    def test_sources_and_author_round_trip_through_the_head(self, experiment: Any) -> None:
        item = _write(experiment)

        reopened = Knowledge.open(item.path)

        assert isinstance(reopened, Finding)
        assert [(s.kind, s.ref) for s in reopened.sources] == [("experiment", experiment.id)]
        assert "created_by: tester" in item.path.read_text()

    def test_a_repeat_write_is_idempotent_on_the_name(self, experiment: Any) -> None:
        _write(experiment, text="first\n")
        second = _write(experiment, text="second\n")

        assert "second" in second.read()
        assert "first" not in Knowledge.open(second.path).read()
        landed = sorted(p.name for p in (Path(str(experiment.resolve())) / "knowledges").iterdir())
        assert landed == ["finding-demo.md"]

    def test_a_knowledge_target_is_cross_referenced(self, experiment: Any) -> None:
        other = mount_note(experiment, "Background", body="# BG\n")

        item = _write(experiment, cite=[(other, "cites")])

        assert [(Path(e.target).name, e.role) for e in item.links()] == [("background.md", "cites")]

    def test_a_folder_target_is_normalized_to_its_directory(self, experiment: Any) -> None:
        item = _write(experiment, cite=[(experiment, "derived_from")])

        edges = item.links()
        assert [(e.target, e.role) for e in edges] == [(str(experiment.resolve()), "derived_from")]

    def test_a_bare_path_target_keeps_its_edge(self, experiment: Any, tmp_path: Path) -> None:
        outside = tmp_path / "outside-family"
        outside.mkdir()

        item = _write(experiment, cite=[(str(outside), "references")])

        # The third branch must not be routed through the embed resolver: that
        # would raise on a non-Folder/Asset target and drop the edge silently.
        assert [(e.target, e.role) for e in item.links()] == [(str(outside), "references")]

    def test_a_failing_cite_never_fails_the_write(self, experiment: Any) -> None:
        item = _write(experiment, cite=[(object(), "references")])

        assert item.exists()
        assert item.read().startswith("# Finding")


class TestMountNote:
    def test_the_first_mount_materializes_without_a_body(self, experiment: Any) -> None:
        note = mount_note(experiment, "An Idea")

        assert isinstance(note, Note)
        assert note.path == folder(experiment, "An Idea", Note)
        assert note.exists(), "an empty-body mount must still materialize the document"
        assert note.read() == ""

    def test_the_body_lands_on_the_creating_call(self, experiment: Any) -> None:
        note = mount_note(experiment, "An Idea", body="# Kept\n")

        assert note.read() == "# Kept\n"

    def test_a_repeat_call_is_idempotent_and_never_truncates(self, experiment: Any) -> None:
        first = mount_note(experiment, "My Idea", body="# Kept\n")
        second = mount_note(experiment, "my-idea", body="")
        third = mount_note(experiment, "my-idea")

        assert second.path == first.path == third.path
        assert second.read() == "# Kept\n"
        assert third.read() == "# Kept\n"

    def test_a_mounted_note_is_visible_to_a_bundle_walk(self, lab: Any, experiment: Any) -> None:
        mount_note(experiment, "log-notes")

        walked = {
            Path(c.path).relative_to(lab.root).as_posix()
            for c in Knowledge(lab.root).walk()
            if type(c).__name__ == "Note"
        }
        experiment_rel = Path(str(experiment.resolve())).relative_to(lab.root).as_posix()

        assert walked == {f"{experiment_rel}/knowledges/log-notes.md"}


class TestNormalizeSources:
    def test_a_source_ref_passes_through(self, experiment: Any) -> None:
        ref = SourceRef(kind="artifact", ref="deadbeef")

        assert normalize_sources([ref], default_host=experiment) == [ref]

    def test_folders_map_to_their_own_kind(self, lab: Any, experiment: Any, run: Any) -> None:
        project = lab.get_project("p")

        got = normalize_sources([run, experiment, project], default_host=experiment)

        assert [(s.kind, s.ref) for s in got] == [
            ("run", run.id),
            ("experiment", experiment.id),
            ("file", project.id),
        ]

    def test_strings_are_classified_by_shape(self, experiment: Any) -> None:
        got = normalize_sources(
            ["DOI:10.1234/xyz", "10.4321/q", "dataset:ab12", "plugin:foo", "notes/raw.txt"],
            default_host=experiment,
        )

        assert [(s.kind, s.ref) for s in got] == [
            ("reference", "DOI:10.1234/xyz"),
            ("reference", "10.4321/q"),
            ("file", "dataset:ab12"),
            ("file", "plugin:foo"),
            ("file", "notes/raw.txt"),
        ]

    def test_an_empty_request_defaults_to_the_host(self, experiment: Any, run: Any) -> None:
        assert normalize_sources(None, default_host=experiment) == [
            SourceRef(kind="experiment", ref=experiment.id)
        ]
        assert normalize_sources([], default_host=run) == [SourceRef(kind="file", ref=run.id)]

    def test_a_literature_class_writes_through_the_same_path(self, experiment: Any) -> None:
        lit = write_knowledge(
            experiment,
            name="Smith 2024",
            of=Literature,
            sources=[SourceRef(kind="reference", ref="10.1/x")],
            created_by="tester",
            text="# Smith 2024\n",
        )

        assert Path(lit.path).name == "smith-2024.md"
        assert Knowledge.open(lit.path).read().startswith("# Smith 2024")
