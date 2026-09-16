"""The workspace ``Bundle`` prunes run-output subtrees without losing knowledge.

Every workspace ``Folder`` carries a ``meta.yaml``, so an OKF walk visits every
project / experiment / run — and, unpruned, every run's ``executions/`` /
``artifacts/`` / ``logs/`` beneath. Knowledge is only ever mounted *directly*
under a Folder, so those subtrees can be skipped.

Pruning is **position-aware**: :class:`~molexp.workspace.run.Run` declares the
subdirectories it *produces* in ``NON_CONCEPT_SUBDIRS``, and the walk skips
those names only among a Run's own children. These tests guard both halves of
that bargain — the run output is never enumerated, *and* a Note that merely
happens to be called ``logs`` or ``source`` anywhere else is still found. The
second half is a regression guard: a global name denylist once made such a
Note invisible to every listing, search and backlink while it sat on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.fs import LocalFileSystem
from molexp.knowledge.bundle import Bundle as KnowledgeBundle
from molexp.knowledge.concept import META_YAML_FILENAME
from molexp.knowledge.types import non_concept_subdirs
from molexp.workspace import Workspace
from molexp.workspace.bundle import WORKSPACE_PRUNE_DIRS, Bundle
from molexp.workspace.concepts import Note, ReferenceConcept
from molexp.workspace.knowledge_item import KnowledgeItem, SourceRef
from molexp.workspace.knowledge_mount import mount_note
from molexp.workspace.knowledge_write import write_knowledge_item
from molexp.workspace.reference_meta import ReferenceMeta
from molexp.workspace.run import Run
from tests.support.counting_fs import CountingFileSystem

KNOWLEDGE_TYPES = (Note, ReferenceConcept, KnowledgeItem)


def _plant_decoy(directory: Path) -> None:
    """A marker where no knowledge is ever mounted — inside run output."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / META_YAML_FILENAME).write_text(f"type: note.note\nid: {directory.name}\n")
    (directory / "index.md").write_text("# decoy\n\nshould never be walked\n")


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Knowledge mounted at root, project, experiment and run, plus decoys."""
    ws = Workspace(root=tmp_path / "lab", name="lab")
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e")
    run = experiment.add_run(params={"x": 1})

    mount_note(ws, "root-note", body="# Root\n\nat the root\n")
    mount_note(project, "project-note", body="# Project\n\nunder the project\n")
    mount_note(experiment, "exp-note", body="# Experiment\n\nunder the experiment\n")
    mount_note(run, "run-note", body="# Run\n\nunder the run\n")
    write_knowledge_item(
        experiment,
        name="finding",
        kind="Finding",
        sources=[SourceRef(kind="run", ref=run.id)],
        created_by="tester",
        body="# Finding\n\nwhat the run taught us\n",
    )
    ref = ReferenceConcept(Path(str(project.resolve())) / "a-paper", fs=ws.fs)
    ref.write_reference_meta(ReferenceMeta(title="A paper", authors=["A"], year=2021))

    run_dir = Path(str(run.resolve()))
    for sub in ("executions/exec-1/nested", "artifacts/blob", "logs/x", "cache/y", "metrics/m"):
        _plant_decoy(run_dir / sub)
    return ws


def _knowledge_rels(bundle: KnowledgeBundle) -> set[str]:
    return {bundle.rel_path(c) for c in bundle.walk() if isinstance(c, KNOWLEDGE_TYPES)}


def _marker_dirs_on_disk(root: Path) -> set[str]:
    """Every directory holding a ``meta.yaml``, straight off the filesystem.

    The reference the walk is judged against — independent of any Bundle, so a
    pruning bug cannot hide from the comparison by being in both sides.
    """
    return {
        marker.parent.relative_to(root).as_posix()
        for marker in Path(root).rglob(META_YAML_FILENAME)
        if marker.parent != Path(root)
    }


def _under_run_output(rel: str) -> bool:
    """Is *rel* inside a run's own output subtree (the deliberately pruned part)?"""
    parts = rel.split("/")
    return any(
        part in WORKSPACE_PRUNE_DIRS and idx > 0 and parts[idx - 1].startswith("run-")
        for idx, part in enumerate(parts)
    )


class TestPrunedWalkEquivalence:
    def test_pruned_walk_yields_every_marker_except_run_output(self, workspace: Workspace) -> None:
        root = workspace.resolve()
        on_disk = _marker_dirs_on_disk(Path(str(root)))
        decoys = {r for r in on_disk if _under_run_output(r)}
        assert decoys, "the fixture must plant markers inside run output"
        walked = {Bundle(root).rel_path(c) for c in Bundle(root).walk()}
        assert walked == on_disk - decoys

    def test_pruning_now_travels_with_the_data_not_the_bundle_class(
        self, workspace: Workspace
    ) -> None:
        # The layout knowledge lives on the registered ``Run`` type, so a plain
        # OKF bundle opened over a workspace prunes identically. The workspace
        # subclass is a named entry point, no longer a behavioural difference.
        root = workspace.resolve()
        assert _knowledge_rels(KnowledgeBundle(root)) == _knowledge_rels(Bundle(root))

    def test_every_mounted_concept_is_reached(self, workspace: Workspace) -> None:
        pruned = _knowledge_rels(Bundle(workspace.resolve()))
        run = workspace.get_project("p").get_experiment("e").list_runs()[0]
        assert pruned == {
            "root-note",
            "projects/p/project-note",
            "projects/p/a-paper",
            "projects/p/experiments/e/exp-note",
            "projects/p/experiments/e/finding",
            f"projects/p/experiments/e/runs/run-{run.id}/run-note",
        }

    def test_entity_folders_are_still_walked_as_concepts(self, workspace: Workspace) -> None:
        # Pruning removes run *output*, not the run itself: the run's marker is
        # still a Concept in the walk (context assembly relies on it).
        bundle = Bundle(workspace.resolve())
        rels = {bundle.rel_path(c) for c in bundle.walk()}
        assert any(
            r.startswith("projects/p/experiments/e/runs/run-") and r.count("/") == 5 for r in rels
        )

    def test_run_output_dirs_are_never_listed(self, workspace: Workspace) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        list(Bundle(workspace.resolve(), fs=fs).walk())
        listed = [path for name, path, _ in fs.log if name == "listdir"]
        for pruned in WORKSPACE_PRUNE_DIRS:
            assert not any(p.rstrip("/").endswith(f"/{pruned}") for p in listed), pruned

    def test_workspace_package_exports_the_pruned_bundle(self) -> None:
        import molexp.workspace as ws_pkg

        assert ws_pkg.Bundle is Bundle
        assert issubclass(Bundle, KnowledgeBundle)
        # Pruning is no longer a global name denylist on the instance: it
        # travels through the concept-type registry and applies only among a
        # Run's own children.
        assert Bundle("/tmp/x").prune_dirs == frozenset({"_ops"})
        assert KnowledgeBundle("/tmp/x").prune_dirs == frozenset({"_ops"})
        assert WORKSPACE_PRUNE_DIRS == Run.NON_CONCEPT_SUBDIRS
        assert non_concept_subdirs("workspace.run") == WORKSPACE_PRUNE_DIRS

    def test_pruning_is_scoped_to_runs_not_to_other_folder_types(self) -> None:
        # The names are meaningless only *inside a run*; no other entity type
        # claims them, which is what keeps a Note called ``logs`` visible.
        for kind in ("workspace.workspace", "workspace.project", "workspace.experiment"):
            assert non_concept_subdirs(kind) == frozenset()


class TestConceptsInPruneNamedDirsStayVisible:
    """A Note whose directory is *named* like run output is still knowledge.

    The regression: pruning used to match a bare directory name at any depth,
    so mounting a Note called ``logs`` (or ``source``, or ``artifacts``) made it
    vanish from every listing, search and backlink — on disk, but invisible.
    """

    @pytest.fixture
    def workspace_with_collisions(self, tmp_path: Path) -> Workspace:
        ws = Workspace(root=tmp_path / "lab", name="lab")
        ws.materialize()
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        experiment.add_run(params={"x": 1})
        for host in (ws, project, experiment):
            for name in ("logs", "source", "artifacts"):
                mount_note(host, name, body=f"# {name}\n\nreal knowledge\n")
        return ws

    @pytest.mark.parametrize("name", ["logs", "source", "artifacts"])
    def test_note_named_like_run_output_is_walked_at_every_level(
        self, workspace_with_collisions: Workspace, name: str
    ) -> None:
        bundle = Bundle(workspace_with_collisions.resolve())
        rels = _knowledge_rels(bundle)
        assert {name, f"projects/p/{name}", f"projects/p/experiments/e/{name}"} <= rels

    def test_partition_and_notes_see_them_too(self, workspace_with_collisions: Workspace) -> None:
        bundle = Bundle(workspace_with_collisions.resolve())
        for names in (
            {bundle.rel_path(n) for n in bundle.notes()},
            {bundle.rel_path(n) for n in bundle.partition().notes},
        ):
            assert {"logs", "projects/p/source", "projects/p/experiments/e/artifacts"} <= names

    def test_run_output_is_still_pruned_on_the_same_tree(
        self, workspace_with_collisions: Workspace
    ) -> None:
        # The fix must not cost the performance property it paid for.
        ws = workspace_with_collisions
        run = ws.get_project("p").get_experiment("e").list_runs()[0]
        run_dir = Path(str(run.resolve()))
        for sub in ("executions/exec-1/nested", "artifacts/blob", "logs/deep"):
            _plant_decoy(run_dir / sub)

        fs = CountingFileSystem(LocalFileSystem())
        rels = {Bundle(ws.resolve()).rel_path(c) for c in Bundle(ws.resolve(), fs=fs).walk()}
        assert not any("/runs/run-" in r and "/blob" in r for r in rels)
        assert not any("/runs/run-" in r and "/nested" in r for r in rels)
        run_rel = f"projects/p/experiments/e/runs/run-{run.id}"
        listed = [p for name, p, _ in fs.log if name == "listdir"]
        for pruned in WORKSPACE_PRUNE_DIRS:
            assert not any(p.rstrip("/").endswith(f"{run_rel}/{pruned}") for p in listed), pruned


class TestConceptUnderRunOutputStaysPruned:
    """Pinned semantics: a marker *inside* a run's output subtree is not knowledge.

    ``harvest`` and ``knowledge_mount`` place Concepts directly under the run
    directory, never beneath ``artifacts/`` — that subtree is machine output,
    and walking it is exactly the cost pruning exists to avoid. A marker found
    there is treated as data that happens to look like a Concept, and stays
    invisible. This is a deliberate trade, pinned so it cannot drift silently.
    """

    def test_marker_inside_run_artifacts_is_not_yielded(self, workspace: Workspace) -> None:
        run = workspace.get_project("p").get_experiment("e").list_runs()[0]
        _plant_decoy(Path(str(run.resolve())) / "artifacts" / "looks-like-a-note")
        rels = _knowledge_rels(Bundle(workspace.resolve()))
        assert not any("looks-like-a-note" in r for r in rels)

    def test_the_same_marker_is_yielded_directly_under_the_run(self, workspace: Workspace) -> None:
        run = workspace.get_project("p").get_experiment("e").list_runs()[0]
        _plant_decoy(Path(str(run.resolve())) / "looks-like-a-note")
        rels = _knowledge_rels(Bundle(workspace.resolve()))
        assert f"projects/p/experiments/e/runs/run-{run.id}/looks-like-a-note" in rels
