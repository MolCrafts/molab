"""``knowledge_mount`` — the ``Folder`` ↔ ``Concept`` adapter.

The workspace stores entities as ``Folder``\\ s (a path composed from a parent
chain) and knowledge as OKF ``Concept``\\ s (a path that *is* the identity).
This module is the one seam between them: it mounts a Concept **directly**
under a Folder host, and translates the two verbs that need both families —
provenance embedding and entity summaries.

These tests pin the seam itself: that a mount lands where the host lives, that
re-mounting is idempotent, that a mounted Concept is visible to a bundle walk
(so it is knowledge, not a stray directory), and that an embed writes exactly
one typed edge whichever family the target belongs to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge.concept import Concept
from molab.workspace import Workspace, knowledge_mount


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab")
    ws.materialize()
    return ws


class TestMountNote:
    def test_mounts_directly_under_each_host_level(self, workspace: Workspace) -> None:
        """A Concept may hang off any Folder — workspace, project, experiment, run."""
        project = workspace.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run(params={"seed": 1})

        for host in (workspace, project, experiment, run):
            note = knowledge_mount.mount_note(host, "notes")
            assert Path(str(note.path)).parent == Path(str(host.resolve())) / "knowledges"
            assert Path(str(note.path)).is_dir()

    def test_is_idempotent_on_the_slug_and_keeps_the_body(self, workspace: Workspace) -> None:
        first = knowledge_mount.mount_note(workspace, "My Idea", body="# Kept\n")
        second = knowledge_mount.mount_note(workspace, "my-idea")

        assert str(first.path) == str(second.path)
        assert second.read() == "# Kept\n"

    def test_a_mounted_note_is_found_by_a_bundle_walk(self, workspace: Workspace) -> None:
        run = workspace.add_project("p").add_experiment("e").add_run(params={"seed": 1})
        knowledge_mount.mount_note(run, "log-notes")

        from molab.knowledge import Knowledge

        root = Knowledge(workspace.root)
        mounted = {
            Path(c.path).relative_to(workspace.root).as_posix()
            for c in root.walk()
            if type(c).__name__ == "Note"
        }

        run_rel = Path(str(run.resolve())).relative_to(workspace.root).as_posix()
        assert mounted == {f"{run_rel}/knowledges/log-notes"}


class TestEmbed:
    def test_embeds_a_folder_target_as_one_typed_edge(self, workspace: Workspace) -> None:
        run = workspace.add_project("p").add_experiment("e").add_run(params={"seed": 1})
        note = knowledge_mount.mount_note(workspace, "idea")

        knowledge_mount.embed(note, run, root=workspace.root)

        edges = note.links()
        assert len(edges) == 1
        # A run is the thing a note *records* — the default role per target kind.
        assert edges[0].role == "records"
        assert Path(edges[0].target).resolve() == Path(str(run.resolve())).resolve()

    def test_embeds_a_concept_target_and_honours_an_explicit_role(
        self, workspace: Workspace
    ) -> None:
        note = knowledge_mount.mount_note(workspace, "idea")
        other = knowledge_mount.mount_note(workspace, "background")

        knowledge_mount.embed(note, other, root=workspace.root, role="cites")

        edges = note.links()
        assert [(e.role, Path(e.target).name) for e in edges] == [("cites", "background")]


class TestEntitySummary:
    def test_summarizes_both_families(self, workspace: Workspace) -> None:
        project = workspace.add_project("p")
        note = knowledge_mount.mount_note(workspace, "idea", body="# Titled\n")

        folder_summary = knowledge_mount.entity_summary(project, root=workspace.root)
        concept_summary = knowledge_mount.entity_summary(note, root=workspace.root)

        assert (folder_summary.id, folder_summary.kind) == (project.id, "workspace.project")
        # A Concept *is* its path, so its directory name is its id.
        assert (concept_summary.id, concept_summary.kind) == ("idea", "note")
        assert concept_summary.title == "Titled"

    def test_rejects_something_that_is_neither(self, workspace: Workspace) -> None:
        with pytest.raises(TypeError):
            knowledge_mount.entity_summary(object(), root=workspace.root)  # ty: ignore[invalid-argument-type]


def test_a_concept_is_not_a_folder(workspace: Workspace) -> None:
    """The two families stay unrelated — that is why the adapter exists."""
    note = knowledge_mount.mount_note(workspace, "idea")
    assert isinstance(note, Concept)
    from molab.workspace.folder import Folder

    assert not isinstance(note, Folder)
