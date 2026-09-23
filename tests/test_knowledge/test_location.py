"""``location.folder`` — the one derivation of where a document lands."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge.concept import Concept
from molab.knowledge.concepts import Finding, Note, Plan
from molab.knowledge.location import folder
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

    def test_a_directory_form_class_keeps_the_directory(self, experiment: Experiment) -> None:
        assert folder(experiment, "records", Concept) == _container(experiment) / "records"

    def test_the_class_decides_the_form_not_a_suffix_in_the_name(
        self, experiment: Experiment
    ) -> None:
        # Same host, same name — only ``of`` differs, and that is the whole rule.
        assert folder(experiment, "tg-rise", Finding) == _container(experiment) / "tg-rise.md"
        assert folder(experiment, "tg-rise", Concept) == _container(experiment) / "tg-rise"

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

        with pytest.raises(TypeError, match="_disk"):
            folder(Coordinate(), "x", Note)

    def test_a_concept_host_is_rejected(self, tmp_path: Path) -> None:
        # A Concept has resolve() and is not a host: it must never receive a
        # silently-invented local filesystem.
        with pytest.raises(TypeError, match="_disk"):
            folder(Note(tmp_path / "other"), "x", Note)

    def test_a_non_path_object_host_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError, match="_disk"):
            folder(42, "x", Note)
