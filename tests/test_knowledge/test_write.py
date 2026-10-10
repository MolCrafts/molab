"""``molab.knowledge.write`` — the sourced writer, the note mount, source normalization.

Three behaviors are load-bearing here and each has its own guard below:

- the destination comes from :func:`molab.knowledge.location.folder` and the
  bytes land through ``Concept.write`` (one derivation, one persistence path);
- the **cite channel keeps all three branches** — a Knowledge document through
  ``.ref``, a ``Folder``/``Asset`` through the embed resolver, and a bare path
  straight to ``append_link``. The third branch must never be routed through the
  resolver: it would raise, and the edge would be silently dropped;
- ``Note.mount`` materializes a document even with an empty body, and a repeat
  call (including ``body=""``) never truncates an existing body.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge import Finding, Knowledge, Literature, Note, SourceRef
from molab.knowledge.location import folder
from molab.workspace.domain import Asset
from molab.workspace.folder import Folder


def _write(experiment: Any, **overrides: Any) -> Knowledge:
    kwargs: dict[str, Any] = {
        "name": "finding-demo",
        "of": Finding,
        "sources": [SourceRef.of(experiment)],
        "created_by": "tester",
        "text": "# Finding\n\nhello\n",
    }
    kwargs.update(overrides)
    of = kwargs.pop("of")
    name = kwargs.pop("name")
    return of.create(experiment, name, **kwargs)


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
        from molab.workspace.refs import ref_of

        assert [(s.kind, s.ref) for s in reopened.sources] == [
            ("experiment", str(ref_of(experiment)))
        ]
        assert "created_by: tester" in item.path.read_text()

    def test_a_repeat_write_is_idempotent_on_the_name(self, experiment: Any) -> None:
        _write(experiment, text="first\n")
        second = _write(experiment, text="second\n")

        assert "second" in second.read()
        assert "first" not in Knowledge.open(second.path).read()
        landed = sorted(p.name for p in (Path(str(experiment.resolve())) / "knowledges").iterdir())
        assert landed == ["finding-demo.md"]

    def test_a_knowledge_target_is_cross_referenced(self, experiment: Any) -> None:
        other = Note.mount(experiment, "Background", body="# BG\n")

        item = _write(experiment, cite=[(other, "cites")])

        cited = [(Path(e.target).name, e.role) for e in item.links() if e.role == "cites"]
        assert cited == [("background.md", "cites")]

    def test_a_folder_target_is_normalized_to_its_directory(self, experiment: Any) -> None:
        item = _write(experiment, cite=[(experiment, "derived_from")])

        from molab.workspace.refs import ref_of

        edges = item.links()
        assert [(e.target, e.role) for e in edges] == [(str(ref_of(experiment)), "derived_from")]

    def test_a_folder_cite_asks_enclosing_root_once(
        self, experiment: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace import Workspace

        calls: list[object] = []
        original = Workspace.enclosing_root

        def spy(path: object, *, fs: object = None) -> object:
            calls.append(path)
            return original(path, fs=fs)  # type: ignore[arg-type]

        monkeypatch.setattr(Workspace, "enclosing_root", staticmethod(spy))

        item = _write(experiment, cite=[(experiment, "derived_from")])

        assert calls == [experiment.resolve()]
        from molab.workspace.refs import ref_of

        assert [(edge.target, edge.role) for edge in item.links()] == [
            (str(ref_of(experiment)), "derived_from")
        ]

    def test_a_bare_path_target_keeps_its_edge(self, experiment: Any, tmp_path: Path) -> None:
        outside = tmp_path / "outside-family"
        outside.mkdir()

        item = _write(experiment, cite=[(str(outside), "references")])

        # The third branch must not be routed through the embed resolver: that
        # would raise on a non-Folder/Asset target and drop the edge silently.
        assert (str(outside), "references") in [(e.target, e.role) for e in item.links()]

    def test_a_failing_cite_never_fails_the_write(self, experiment: Any) -> None:
        item = _write(experiment, cite=[(object(), "references")])

        assert item.exists()
        assert item.read().startswith("# Finding")

    def test_a_domain_asset_cite_writes_exactly_one_edge(
        self, experiment: Any, tmp_path: Path
    ) -> None:
        source = tmp_path / "mydata.txt"
        source.write_text("payload-bytes")
        asset = experiment.assets.import_asset("mydata", source)
        assert isinstance(asset, Asset)

        from molab.workspace.refs import ref_of

        item = _write(experiment, cite=[(asset, "references")])

        assert [edge.target for edge in item.links() if edge.role == "references"] == [
            str(ref_of(asset))
        ]


class TestMountNote:
    def test_the_first_mount_materializes_without_a_body(self, experiment: Any) -> None:
        note = Note.mount(experiment, "An Idea")

        assert isinstance(note, Note)
        assert note.path == folder(experiment, "An Idea", Note)
        assert note.exists(), "an empty-body mount must still materialize the document"
        assert note.read() == ""

    def test_the_body_lands_on_the_creating_call(self, experiment: Any) -> None:
        note = Note.mount(experiment, "An Idea", body="# Kept\n")

        assert note.read() == "# Kept\n"

    def test_a_repeat_call_is_idempotent_and_never_truncates(self, experiment: Any) -> None:
        first = Note.mount(experiment, "My Idea", body="# Kept\n")
        second = Note.mount(experiment, "my-idea", body="")
        third = Note.mount(experiment, "my-idea")

        assert second.path == first.path == third.path
        assert second.read() == "# Kept\n"
        assert third.read() == "# Kept\n"

    def test_a_mounted_note_is_visible_to_a_bundle_walk(self, lab: Any, experiment: Any) -> None:
        Note.mount(experiment, "log-notes")

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

        assert SourceRef.normalize([ref], default_host=experiment) == [ref]

    def test_folders_map_to_their_own_kind(self, lab: Any, experiment: Any, run: Any) -> None:
        project = lab.get_project("p")

        from molab.workspace.refs import ref_of

        got = SourceRef.normalize([run, experiment, project], default_host=experiment)

        assert [(s.kind, s.ref) for s in got] == [
            ("run", str(ref_of(run))),
            ("experiment", str(ref_of(experiment))),
            ("project", str(ref_of(project))),
        ]

    def test_strings_are_classified_by_shape(self, experiment: Any) -> None:
        got = SourceRef.normalize(
            ["DOI:10.1234/xyz", "10.4321/q", "dataset:ab12", "plugin:foo", "notes/raw.txt"],
            default_host=experiment,
        )

        assert [(s.kind, s.ref) for s in got] == [
            ("reference", "https://doi.org/10.1234/xyz"),
            ("reference", "https://doi.org/10.4321/q"),
            ("file", "dataset:ab12"),
            ("file", "plugin:foo"),
            ("file", "notes/raw.txt"),
        ]

    def test_an_empty_request_defaults_to_the_host(self, experiment: Any, run: Any) -> None:
        from molab.knowledge.write import normalize_sources

        assert SourceRef.normalize(None, default_host=experiment) == [SourceRef.of(experiment)]
        assert normalize_sources([], default_host=run) == [SourceRef.of(run)]

    def test_a_literature_class_writes_through_the_same_path(self, experiment: Any) -> None:
        lit = Literature.create(
            experiment,
            "Smith 2024",
            sources=[SourceRef(kind="reference", ref="10.1/x")],
            created_by="tester",
            text="# Smith 2024\n",
        )

        assert Path(lit.path).name == "smith-2024.md"
        assert Knowledge.open(lit.path).read().startswith("# Smith 2024")


class TestWriteKnowledgePath:
    def test_a_workspace_root_and_a_bare_handle_land_in_knowledges(
        self, lab: Any, tmp_path: Path
    ) -> None:
        from molab.knowledge.write import write_knowledge

        rooted = write_knowledge(lab, name="Lab Notes", of=Note, created_by="t", text="# Lab\n")
        assert rooted.path == Path(lab.root) / "knowledges" / "lab-notes.md"
        via_handle = write_knowledge(
            Knowledge(lab.root), name="Root Note", of=Note, created_by="t", text="# Root\n"
        )
        assert via_handle.path == Path(lab.root) / "knowledges" / "root-note.md"

        wiki = tmp_path / "wiki"
        wiki.mkdir()
        page = write_knowledge(Knowledge(wiki), name="Tg", of=Note, created_by="t", text="# Tg\n")
        assert page.path == wiki / "tg.md"

    def test_literature_needs_no_sources_and_keeps_a_record(self, lab: Any) -> None:
        from molab.knowledge.reference_meta import ReferenceMeta
        from molab.knowledge.write import write_knowledge

        item = write_knowledge(
            lab,
            name="Paper",
            of=Literature,
            created_by="t",
            text="",
            record=ReferenceMeta(title="T"),
        )
        assert item.frontmatter()["title"] == "T"

    def test_a_sourced_class_still_requires_sources(self, experiment: Any) -> None:
        from molab.knowledge.write import write_knowledge

        with pytest.raises(ValueError):
            write_knowledge(experiment, name="f", of=Finding, created_by="t", text="# F\n")

    def test_an_empty_rewrite_keeps_the_body(self, lab: Any) -> None:
        from molab.knowledge.write import write_knowledge

        item = write_knowledge(lab, name="Lab Notes", of=Note, created_by="t", text="# Lab\n")
        write_knowledge(lab, name="Lab Notes", of=Note, created_by="t", text="")
        assert item.read() == "# Lab\n"

    def test_history_records_a_create_once_and_never_blocks(
        self, lab: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.knowledge.write import write_knowledge
        from molab.workspace.history import GitHistory

        calls: list[tuple[str, str, str]] = []

        def spy(self: object, event: str, **kwargs: Any) -> str:
            subject = kwargs["subject"]
            calls.append((event, subject.type, subject.id))
            return "sha"

        monkeypatch.setattr(GitHistory, "record", spy)
        write_knowledge(lab, name="Lab Notes", of=Note, created_by="t", text="# Lab\n")
        assert calls == [("knowledge.created", "Note", "knowledges/lab-notes.md")]
        write_knowledge(lab, name="Lab Notes", of=Note, created_by="t", text="# Lab\n")
        assert calls == [("knowledge.created", "Note", "knowledges/lab-notes.md")]

        wiki = tmp_path / "wiki"
        wiki.mkdir()
        before = len(calls)
        write_knowledge(Knowledge(wiki), name="Tg", of=Note, created_by="t", text="# Tg\n")
        assert len(calls) == before

        def boom(self: object, event: str, **kwargs: Any) -> str:
            raise RuntimeError("history down")

        monkeypatch.setattr(GitHistory, "record", boom)
        made = write_knowledge(lab, name="Still", of=Note, created_by="t", text="# Still\n")
        assert made.path.name == "still.md"
