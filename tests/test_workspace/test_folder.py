"""Tests for ``molab.workspace.folder`` — the abstract ``Folder`` base class.

Covers the ``Folder`` lifecycle (lazy mkdir, atomic ``write_json``, id/kind
validation, ``children`` filtering, metadata round-trip, ``delete`` / ``move_to``)
and the two Folder type tables: the filename axis this module owns
(``register_entity_class`` / ``class_for_entity_file`` / ``entity_json_names``)
and the ``meta.json`` ``type`` axis ``concept_from_dir`` consumes. The
folder-module import-guard subprocess lives at the bottom.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from molab.workspace import Experiment, Project, Run, Workspace
from molab.workspace import folder as folder_mod
from molab.workspace.folder import (
    Folder,
    FolderMoveCollisionError,
    class_for_entity_file,
    class_for_folder_type,
    concept_from_dir,
    entity_filename,
    entity_json_names,
    register_entity_class,
    register_folder_type,
)


# ``Folder`` has no business subclasses at this level; this private subclass
# exists only so ``children()`` has something concrete to reconstruct. It is a
# production-shaped registrar too, so it also proves the filename axis takes a
# class registered from anywhere.
@register_entity_class
class _TestSubFolder(Folder):
    """Minimal Folder subclass used only by the children() filter test."""


class TestFolder:
    def test_construction_is_side_effect_free_then_path_lazily_mkdirs(self, tmp_path: Path) -> None:
        """Construction touches no filesystem; the first ``path()`` mkdirs, and
        a second ``path()`` is an idempotent no-op returning the same Path."""
        folder = Folder(parent=None, name="alpha", kind="test.root", root_path=tmp_path)

        target = tmp_path / "alpha"
        assert not target.exists(), "construction must be side-effect-free"

        first = Path(folder.path)
        assert first == target
        assert first.is_dir()
        assert Path(folder.path) == first  # idempotent

    @pytest.mark.parametrize(
        "name, valid",
        [
            ("ok-1", True),
            ("UPPER", False),  # uppercase rejected
            ("../etc", False),  # path traversal rejected
            ("", False),  # empty rejected
            ("!!!", False),  # all-punctuation slugifies to empty
        ],
    )
    def test_name_is_slugified_and_validated(self, tmp_path: Path, name: str, valid: bool) -> None:
        """``slugify(name)`` must yield an id matching ``_KIND_PATTERN``;
        otherwise ``ValueError`` at construction."""
        if valid:
            Folder(parent=None, name=name, kind="test.root", root_path=tmp_path)
        else:
            with pytest.raises(ValueError):
                Folder(parent=None, name=name, kind="test.root", root_path=tmp_path)

    @pytest.mark.parametrize(
        "kind, valid",
        [
            ("workspace.project", True),
            ("WORKSPACE.foo", False),  # uppercase rejected
            (".leading", False),  # leading dot rejected
            ("../etc", False),  # path traversal rejected
            ("", False),  # empty rejected
            ("foo bar", False),  # invalid char rejected
        ],
    )
    def test_kind_is_validated(self, tmp_path: Path, kind: str, valid: bool) -> None:
        """``kind`` must be dotted lowercase ASCII (``_KIND_PATTERN``)."""
        if valid:
            Folder(parent=None, name="alpha", kind=kind, root_path=tmp_path)
        else:
            with pytest.raises(ValueError):
                Folder(parent=None, name="alpha", kind=kind, root_path=tmp_path)

    def test_construction_shapes_parent_vs_root_path(self, tmp_path: Path) -> None:
        """``parent=None`` + ``root_path=None`` is the unmounted state (legal at
        construction; ``.path`` raises until mounted). ``parent`` + ``root_path``
        both set is a ``ValueError``. Nesting walks parent→child correctly."""
        unmounted = Folder(parent=None, name="alpha", kind="test.root", root_path=None)
        assert unmounted._parent is None
        with pytest.raises(RuntimeError, match="unmounted"):
            Path(unmounted.path)

        other = Folder(parent=None, name="other", kind="test.root", root_path=tmp_path)
        with pytest.raises(ValueError):
            Folder(parent=other, name="beta", kind="test.child", root_path=tmp_path)

        root = Folder(parent=None, name="root", kind="test.root", root_path=tmp_path)
        mid = Folder(parent=root, name="mid", kind="test.mid")
        leaf = Folder(parent=mid, name="leaf", kind="test.leaf")
        assert Path(leaf.path) == Path(root.path) / "mid" / "leaf"

    def test_children_lists_materialized_subfolders_and_filters_by_kind(
        self, tmp_path: Path
    ) -> None:
        """``children()`` lists materialized subfolders and filters by ``kind=``;
        a non-materialized parent returns ``[]`` without a mkdir side effect."""
        fresh = Folder(parent=None, name="fresh", kind="test.root", root_path=tmp_path)
        assert fresh.children() == []
        assert not (tmp_path / "fresh").exists(), "children() must not mkdir"

        parent = Folder(parent=None, name="parent", kind="test.root", root_path=tmp_path)
        for name, kind in (
            ("alpha1", "test.alpha"),
            ("alpha2", "test.alpha"),
            ("beta", "test.beta"),
        ):
            _TestSubFolder(parent=parent, name=name, kind=kind).materialize()

        assert len(parent.children()) == 3
        assert all(isinstance(c, Folder) for c in parent.children())
        assert {c.metadata.name for c in parent.children(kind="test.alpha")} == {"alpha1", "alpha2"}
        assert [c.metadata.name for c in parent.children(kind="test.beta")] == ["beta"]

    def test_save_bumps_updated_at_past_created_at(self, tmp_path: Path) -> None:
        """``save()`` advances ``updated_at`` in ``meta.json`` (sole concept file)."""
        folder = Folder(parent=None, name="alpha", kind="test.root", root_path=tmp_path)
        folder.materialize()
        meta_path = Path(folder.path) / "meta.json"
        assert meta_path.is_file()
        assert not (Path(folder.path) / "metadata.json").exists()

        time.sleep(0.001)  # let the clock tick so the bump is observable
        folder.save()

        raw = json.loads(meta_path.read_text())
        assert raw["type"] == "test.root"
        created = raw["created_at"]
        updated = raw["updated_at"]
        assert updated > created

    def test_delete_removes_directory_tree(self, tmp_path: Path) -> None:
        """``delete()`` removes the directory tree (including nested files)."""
        folder = Folder(parent=None, name="alpha", kind="test.root", root_path=tmp_path)
        folder.materialize()
        folder.write_json("file.json", {})

        captured = Path(folder.path)  # capture before delete (re-path would re-mkdir)
        assert captured.exists()
        folder.delete()
        assert not captured.exists()

    def test_move_to_relocates_and_bumps_updated_at(self, tmp_path: Path) -> None:
        """``move_to(new_parent)`` relocates on disk, reparents, and bumps
        ``updated_at``."""
        parent_a = Folder(parent=None, name="parent_a", kind="test.root", root_path=tmp_path)
        parent_b = Folder(parent=None, name="parent_b", kind="test.root", root_path=tmp_path)

        folder = Folder(parent=parent_a, name="movable", kind="test.child")
        folder.materialize()
        old_path = Path(folder.path)
        before = folder.metadata.updated_at

        time.sleep(0.001)
        folder.move_to(parent_b)

        assert not old_path.exists()
        assert folder.parent is parent_b
        assert Path(folder.path) == Path(parent_b.path) / "movable"
        assert Path(folder.path).exists()
        assert folder.metadata.updated_at > before

    def test_move_to_collision_raises(self, tmp_path: Path) -> None:
        """``move_to`` raises ``FolderMoveCollisionError`` when the target exists."""
        parent_a = Folder(parent=None, name="parent_a", kind="test.root", root_path=tmp_path)
        parent_b = Folder(parent=None, name="parent_b", kind="test.root", root_path=tmp_path)

        folder = Folder(parent=parent_a, name="movable", kind="test.child")
        folder.materialize()
        Path(parent_b.path).joinpath("movable").mkdir(parents=True, exist_ok=True)

        with pytest.raises(FolderMoveCollisionError):
            folder.move_to(parent_b)

    @pytest.mark.parametrize("bad_name", ["a/b.json", ".."])
    def test_write_json_rejects_path_separators_and_traversal(
        self, tmp_path: Path, bad_name: str
    ) -> None:
        """``write_json`` rejects names with path separators or ``.``/``..``."""
        folder = Folder(parent=None, name="alpha", kind="test.root", root_path=tmp_path)
        folder.materialize()
        with pytest.raises(ValueError):
            folder.write_json(bad_name, {})


def _marker_dir(root: Path, name: str, marker: dict[str, object]) -> Path:
    """A bare ``meta.json``-only directory (no class-named entity JSON)."""
    child = Path(root) / "root" / name
    child.mkdir(parents=True, exist_ok=True)
    (child / "meta.json").write_text(json.dumps(marker), encoding="utf-8")
    return child


class TestFolderTypeRegistry:
    """The ``meta.json`` ``type`` → Folder class table (``register_folder_type``)."""

    def test_registered_type_resolves_to_its_class(self) -> None:
        @register_folder_type("test.folder.type")
        class _Registered(Folder):
            """Test-only Folder subclass."""

        assert class_for_folder_type("test.folder.type") is _Registered

    def test_decorator_returns_the_same_class(self) -> None:
        class _Passthrough(Folder):
            """Test-only Folder subclass."""

        assert register_folder_type("test.folder.passthrough")(_Passthrough) is _Passthrough

    def test_same_class_may_re_claim_its_type(self) -> None:
        @register_folder_type("test.folder.idempotent")
        class _Idempotent(Folder):
            """Test-only Folder subclass."""

        assert register_folder_type("test.folder.idempotent")(_Idempotent) is _Idempotent
        assert class_for_folder_type("test.folder.idempotent") is _Idempotent

    def test_a_different_class_cannot_re_claim_a_type(self) -> None:
        @register_folder_type("test.folder.conflict")
        class _First(Folder):
            """Test-only Folder subclass."""

        class _Second(Folder):
            """Test-only Folder subclass."""

        with pytest.raises(ValueError, match="already claimed"):
            register_folder_type("test.folder.conflict")(_Second)
        assert class_for_folder_type("test.folder.conflict") is _First

    @pytest.mark.parametrize("type_str", ["no.such.type", ""])
    def test_unknown_type_has_no_class(self, type_str: str) -> None:
        assert class_for_folder_type(type_str) is None

    def test_concept_from_dir_rebuilds_a_registered_type(self, tmp_path: Path) -> None:
        """A ``meta.json``-only dir with a registered type rebuilds as that class."""

        @register_folder_type("test.folder.rebuild")
        class _Rebuilt(Folder):
            """Test-only Folder subclass."""

        parent = Folder(name="root", kind="test.root", root_path=tmp_path)
        child = _marker_dir(tmp_path, "alpha", {"type": "test.folder.rebuild", "id": "d"})

        rebuilt = concept_from_dir(str(child), parent)
        assert isinstance(rebuilt, _Rebuilt)
        assert rebuilt.metadata.kind == "test.folder.rebuild"

    def test_concept_from_dir_falls_back_to_plain_folder(self, tmp_path: Path) -> None:
        """An unregistered ``meta.json`` type still rebuilds as a bare ``Folder``."""
        parent = Folder(name="root", kind="test.root", root_path=tmp_path)
        child = _marker_dir(tmp_path, "beta", {"type": "test.folder.unknown", "id": "d"})

        rebuilt = concept_from_dir(str(child), parent)
        assert type(rebuilt) is Folder


class TestFolderTypeTable:
    """The filename axis of the one Folder type table, and its ``concept_from_dir`` read."""

    def test_entity_filename_is_the_class_name_snake_cased(self) -> None:
        assert entity_filename(_TestSubFolder) == "__test_sub_folder.json"
        assert entity_filename(Workspace) == "workspace.json"

    def test_a_registered_class_is_reachable_by_its_entity_file(self) -> None:
        assert class_for_entity_file(entity_filename(_TestSubFolder)) is _TestSubFolder

    def test_an_unknown_entity_file_has_no_class(self) -> None:
        assert class_for_entity_file("finding.json") is None

    def test_entity_json_names_leads_with_the_four_core_levels(self) -> None:
        # Exact equality is asserted fresh-process by the 09 regression script;
        # in-suite ``_TestSubFolder`` is registered too, so assert the prefix.
        assert entity_json_names()[:4] == (
            "workspace.json",
            "project.json",
            "experiment.json",
            "run.json",
        )

    def test_re_registering_the_same_class_adds_no_second_name(self) -> None:
        before = entity_json_names()

        register_entity_class(_TestSubFolder)

        assert entity_json_names() == before

    def test_concept_from_dir_rebuilds_every_built_in_level(self, tmp_path: Path) -> None:
        """The four tree levels rebuild from their own entity filename — no
        knowledge registry involved."""
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        proj = ws.add_project("p")
        exp = proj.add_experiment("e")
        run = exp.add_run(id="r")

        assert type(concept_from_dir(ws.resolve(), ws)) is Workspace
        assert type(concept_from_dir(proj.resolve(), ws)) is Project
        assert type(concept_from_dir(exp.resolve(), proj)) is Experiment
        assert type(concept_from_dir(run.resolve(), exp)) is Run

    def test_a_directory_with_no_marker_is_not_a_folder(self, tmp_path: Path) -> None:
        """No entity record and no ``meta.json`` → ``TypeError``, not a bare Folder."""
        parent = Folder(name="root", kind="test.root", root_path=tmp_path)
        bare = Path(parent.path) / "bare"
        bare.mkdir(parents=True, exist_ok=True)
        (bare / "index.md").write_text("# no marker\n")

        with pytest.raises(TypeError, match="is not a Folder"):
            concept_from_dir(str(bare), parent)

    def test_a_knowledge_directory_is_not_a_folder(self, tmp_path: Path) -> None:
        """A Knowledge document (``finding.json`` + ``index.md``, no entity record)
        is refused the same way — without knowledge's head-file list."""
        parent = Folder(name="root", kind="test.root", root_path=tmp_path)
        doc = Path(parent.path) / "finding"
        doc.mkdir(parents=True, exist_ok=True)
        (doc / "finding.json").write_text("{}")
        (doc / "index.md").write_text("# a finding\n")

        with pytest.raises(TypeError, match="is not a Folder"):
            concept_from_dir(str(doc), parent)


class TestFolderModuleCut:
    """``folder.py`` owns its type tables and nothing of knowledge's vocabulary."""

    def test_folder_module_imports_nothing_from_knowledge(self) -> None:
        tree = ast.parse(Path(folder_mod.__file__).read_text(encoding="utf-8"))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [
                    alias.name
                    for alias in node.names
                    if alias.name == "molab.knowledge" or alias.name.startswith("molab.knowledge.")
                ]
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and (node.module == "molab.knowledge" or node.module.startswith("molab.knowledge."))
            ):
                offenders.append(node.module)

        assert offenders == [], f"folder.py still imports knowledge: {offenders}"

    def test_the_duplicated_edge_machinery_is_gone(self) -> None:
        """The canonical markdown-edge pair is ``molab.knowledge``'s, not ours."""
        assert not hasattr(folder_mod, "LinkScan")
        assert not hasattr(folder_mod, "append_link")
        for name in ("links", "out_edges", "typed_out_edges"):
            assert not hasattr(Folder, name), f"Folder.{name} still exists"

    def test_the_workspace_owned_readers_survive(self) -> None:
        """``index.md`` narrative access and entity-record reading are Folder's own."""
        for name in ("read_index", "write_index", "read_meta", "from_disk", "children"):
            assert hasattr(Folder, name), f"Folder.{name} was removed with the edge cut"
        assert folder_mod.INDEX_FILENAME == "index.md"
        assert folder_mod.META_JSON_FILENAME == "meta.json"


def test_import_guard_folder_pulls_no_upstream_layer() -> None:
    """``import molab.workspace.folder`` pulls no upstream layer (workflow /
    agent) nor ``pydantic_ai`` / ``pydantic_graph`` into ``sys.modules``.
    Subprocess-isolated because the in-process interpreter has those loaded."""
    code = (
        "import sys\n"
        "import molab.workspace.folder  # noqa: F401\n"
        "for mod in ('molab.workflow', 'molab.harness.agent', 'pydantic_ai', 'pydantic_graph'):\n"
        "    assert mod not in sys.modules, "
        "        f'molab.workspace.folder eagerly imported {mod}'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, check=False)
    if result.returncode != 0:
        print("stderr:", result.stderr.decode())
        print("stdout:", result.stdout.decode())
    assert result.returncode == 0, "import-guard subprocess failed; see captured stderr above"
