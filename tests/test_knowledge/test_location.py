"""``location.folder`` — the one derivation of where a document lands."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge.concept import Concept, Knowledge
from molab.knowledge.concepts import Finding, Note, Plan, Report
from molab.knowledge.location import (
    bare_container,
    document_slug,
    enclosing_workspace_root,
    folder,
    host_of,
    is_workspace_root,
)
from molab.workspace import Experiment, Workspace


@pytest.fixture
def experiment(tmp_path: Path) -> Experiment:
    """A real workspace Experiment — the Folder-family host."""
    workspace = Workspace(root=tmp_path / "lab")
    workspace.materialize()
    return workspace.add_project("p").add_experiment("e")


def _container(host: Experiment) -> Path:
    """``<host>/knowledges`` — the container *folder* lands documents in."""
    return Path(str(host.resolve())) / "knowledges"


class TestFolder:
    """One host + one name + the Knowledge class ⇒ that document's own path."""

    def test_a_file_document_class_lands_on_the_markdown_path(self, experiment: Experiment) -> None:
        assert folder(experiment, "Tg Cooling", Note) == _container(experiment) / "tg-cooling.md"

    def test_a_bare_class_is_not_a_document(self, experiment: Experiment) -> None:
        with pytest.raises(TypeError, match="not a knowledge document"):
            folder(experiment, "records", Concept)

    def test_the_class_decides_the_form_not_a_suffix_in_the_name(
        self, experiment: Experiment
    ) -> None:
        assert folder(experiment, "tg-rise", Finding) == _container(experiment) / "tg-rise.md"
        with pytest.raises(TypeError, match="not a knowledge document"):
            folder(experiment, "tg-rise", Concept)

    def test_a_str_host_is_used_as_given(self, tmp_path: Path) -> None:
        host = str(tmp_path / "wiki")
        assert folder(host, "x", Note) == Path(host) / "knowledges" / "x.md"

    def test_a_path_host_with_a_dotdot_segment_is_returned_verbatim(self, tmp_path: Path) -> None:
        # Proof the path host is not resolved: a Folder would collapse it.
        host = tmp_path / "wiki" / ".." / "wiki"

        landed = folder(host, "plan-book", Plan)

        assert landed == Path(str(host)) / "knowledges" / "plan-book.md"
        assert ".." in landed.parts

    def test_a_non_ascii_name_falls_back_to_the_raw_name(self, experiment: Experiment) -> None:
        assert folder(experiment, "冷却", Note) == _container(experiment) / "冷却.md"

    def test_an_already_slugged_name_is_idempotent(self, experiment: Experiment) -> None:
        assert folder(experiment, "My Idea", Note) == folder(experiment, "my-idea", Note)

    def test_the_derivation_is_pure(self, tmp_path: Path) -> None:
        folder(tmp_path, "x", Note)

        assert not (tmp_path / "knowledges").exists()

    def test_an_object_host_without_a_disk_is_rejected(self, tmp_path: Path) -> None:
        # A resolve()-only stand-in for a run / experiment coordinate: the host
        # protocol is _disk()'s existence, never resolve()'s.
        class Coordinate:
            def resolve(self) -> Path:
                return tmp_path

        with pytest.raises(TypeError, match="Folder"):
            folder(Coordinate(), "x", Note)

    def test_a_concept_host_is_rejected(self, tmp_path: Path) -> None:
        # A Concept has resolve() and fs, and is not a Folder host.
        with pytest.raises(TypeError, match="Folder"):
            folder(Note(tmp_path / "other"), "x", Note)

    def test_a_non_path_object_host_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Folder"):
            folder(42, "x", Note)

    def test_a_duck_typed_resolve_and_fs_is_rejected(self, tmp_path: Path) -> None:
        class Duck:
            def resolve(self) -> Path:
                return tmp_path

            @property
            def fs(self) -> object:
                return object()

        with pytest.raises(TypeError, match="Folder"):
            folder(Duck(), "x", Note)

    def test_a_uuid7_suffix_survives_the_slug(self, tmp_path: Path) -> None:
        name = "failure-analysis-0190f0e2-7c1a-7d4e-9b2a-3c4d5e6f7a8b"
        assert folder(tmp_path, name, Report).name == f"{name}.md"
        other = "experiment-record-0190f0e2-7c1a-7d4e-9b2a-3c4d5e6f7a8b"
        assert folder(tmp_path, other, Report).name == f"{other}.md"

    def test_a_bare_handle_uses_the_one_container_rule(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        lab = Workspace(root=tmp_path / "lab", name="Lab")
        lab.materialize()
        experiment = lab.add_project("p").add_experiment("e")

        assert folder(Knowledge(wiki), "Cooling", Note) == wiki / "cooling.md"
        assert (
            folder(Knowledge(lab.root), "Cooling", Note)
            == Path(lab.root) / "knowledges" / "cooling.md"
        )
        with pytest.raises(TypeError, match="inside workspace"):
            folder(Knowledge(experiment.resolve()), "Cooling", Note)

    def test_a_string_host_still_lands_under_knowledges(self, tmp_path: Path) -> None:
        assert folder(tmp_path, "Cooling", Note) == tmp_path / "knowledges" / "cooling.md"


class TestDocumentSlug:
    def test_a_long_name_stops_at_200_characters(self) -> None:
        assert document_slug("a" * 210) == "a" * 200

    def test_a_cjk_name_is_kept(self) -> None:
        assert document_slug("降温速率") == "降温速率"


class TestHostOf:
    def test_knowledges_files_belong_to_the_grandparent(self, tmp_path: Path) -> None:
        lab = tmp_path / "lab"
        experiment = lab / "projects" / "p" / "experiments" / "e"
        assert host_of(lab / "knowledges" / "x.md") == lab
        assert host_of(experiment / "knowledges" / "x.md") == experiment

    def test_a_wiki_file_belongs_to_the_wiki(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        assert host_of(wiki / "x.md") == wiki


class TestEnclosingWorkspaceRoot:
    def test_a_workspace_member_resolves_and_a_wiki_does_not(self, tmp_path: Path) -> None:
        lab = Workspace(root=tmp_path / "lab", name="Lab")
        lab.materialize()
        experiment = lab.add_project("p").add_experiment("e")
        wiki = tmp_path / "wiki"
        wiki.mkdir()

        assert enclosing_workspace_root(lab.root, fs=lab.fs) == lab.root
        assert enclosing_workspace_root(experiment.resolve(), fs=lab.fs) == lab.root
        assert (
            enclosing_workspace_root(Path(lab.root) / "knowledges" / "x.md", fs=lab.fs) == lab.root
        )
        assert enclosing_workspace_root(wiki, fs=lab.fs) is None

    def test_the_lookup_goes_through_the_workspace_accessor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lab = Workspace(root=tmp_path / "lab", name="Lab")
        lab.materialize()
        calls: list[object] = []
        original = Workspace.enclosing_root

        def spy(path: object, *, fs: object = None) -> object:
            calls.append(path)
            return original(path, fs=fs)  # type: ignore[arg-type]

        monkeypatch.setattr(Workspace, "enclosing_root", staticmethod(spy))
        assert enclosing_workspace_root(lab.root, fs=lab.fs) == lab.root
        assert calls == [lab.root]


class TestIsWorkspaceRoot:
    def test_only_the_workspace_root_itself(self, tmp_path: Path) -> None:
        lab = Workspace(root=tmp_path / "lab", name="Lab")
        lab.materialize()
        experiment = lab.add_project("p").add_experiment("e")
        wiki = tmp_path / "wiki"
        wiki.mkdir()

        assert is_workspace_root(lab.root, fs=lab.fs) is True
        assert is_workspace_root(experiment.resolve(), fs=lab.fs) is False
        assert is_workspace_root(wiki, fs=lab.fs) is False


class TestBareContainer:
    def test_root_wiki_and_inner_directory(self, tmp_path: Path) -> None:
        lab = Workspace(root=tmp_path / "lab", name="Lab")
        lab.materialize()
        experiment = lab.add_project("p").add_experiment("e")
        wiki = tmp_path / "wiki"
        wiki.mkdir()

        assert bare_container(lab.root, fs=lab.fs) == Path(lab.root) / "knowledges"
        assert bare_container(wiki, fs=lab.fs) == wiki
        with pytest.raises(TypeError, match="inside workspace"):
            bare_container(experiment.resolve(), fs=lab.fs)
