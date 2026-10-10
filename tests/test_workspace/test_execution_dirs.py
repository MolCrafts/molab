"""The Execution's directories are peers, and their meaning is data."""

from __future__ import annotations

import pytest

from molab.workspace.execution_dirs import (
    ARTIFACTS,
    OUT,
    WORK,
    ExecutionDir,
    UnknownExecutionDirError,
    execution_dir_names,
    list_execution_dirs,
    product_dirs,
    register_execution_dir,
    resolve_execution_dir,
    scratch_dirs,
)


class TestTheThreeTiers:
    def test_all_three_are_declared(self):
        names = execution_dir_names()
        assert {"work", "out", "artifacts"} <= names

    def test_only_the_promoted_tier_enters_the_history(self):
        # out/ holds trajectories and restarts: keeping them would make the
        # history unusable. artifacts/ is what a paper cites.
        assert ARTIFACTS.versioned is True
        assert OUT.versioned is False
        assert WORK.versioned is False

    def test_scratch_is_not_a_place_readers_look(self):
        # A half-written intermediate matching a reader's pattern must not be
        # charted as though it were a result.
        assert WORK.products is False
        assert OUT.products is True
        assert ARTIFACTS.products is True


class TestPeerStatus:
    def test_no_directory_carries_a_rank(self):
        # Equality is structural: the declaration has no priority/order field
        # to express one directory outranking another.
        assert not hasattr(ARTIFACTS, "priority")
        assert set(ExecutionDir.__dataclass_fields__) == {
            "name",
            "purpose",
            "versioned",
            "products",
            "prunable",
        }

    def test_every_directory_explains_itself(self):
        # ``purpose`` is what the UI shows and what a person reads; a blank
        # one would make a directory unexplainable in the file tree.
        for directory in list_execution_dirs():
            assert directory.purpose.strip()


class TestQueryingReplacesHardCoding:
    def test_products_are_found_by_property_not_by_name(self):
        assert {d.name for d in product_dirs()} == {"out", "artifacts"}

    def test_scratch_is_found_by_property_not_by_name(self):
        assert {d.name for d in scratch_dirs()} == {"out", "work"}

    def test_the_promoted_tier_is_searched_before_the_raw_one(self):
        # Same result, two copies: a searcher wants the registered one.
        names = [d.name for d in product_dirs()]
        assert names.index("artifacts") < names.index("out")


class TestRegistrationIsOpen:
    def test_a_package_can_declare_the_directory_it_writes(self):
        register_execution_dir(
            ExecutionDir(
                name="test-plugin-dir",
                purpose="Declared by a test.",
                versioned=False,
                products=True,
            )
        )
        try:
            assert resolve_execution_dir("test-plugin-dir").products is True
            assert "test-plugin-dir" in {d.name for d in product_dirs()}
        finally:
            from molab.workspace import execution_dirs as mod

            mod._REGISTRY.pop("test-plugin-dir")
            mod._ORDER.remove("test-plugin-dir")

    def test_registering_twice_replaces_rather_than_raises(self):
        # A package imported twice must not blow up at import time.
        register_execution_dir(WORK)
        register_execution_dir(WORK)
        assert [d.name for d in list_execution_dirs()].count("work") == 1


class TestUndeclaredNamesAreRefused:
    def test_resolving_an_unknown_directory_raises(self):
        with pytest.raises(UnknownExecutionDirError) as excinfo:
            resolve_execution_dir("outputs")
        # The message names what *is* declared, so the fix is obvious.
        assert "artifacts" in str(excinfo.value)


class TestPrunableDirs:
    """Which directories a prune may remove is data (arch-own-01-cleanup)."""

    def test_seeded_prunable_dirs_are_the_bulk_tiers(self):
        from molab.workspace.execution_dirs import prunable_dirs

        assert {d.name for d in prunable_dirs()} == {"out", "work", "jobs", "checkpoints"}

    def test_promoted_tier_is_not_prunable(self):
        # ``Artifact.path`` points at these bytes; pruning them would dangle it.
        assert ARTIFACTS.prunable is False

    def test_undeclared_prunability_defaults_to_kept(self):
        from molab.workspace import execution_dirs as mod
        from molab.workspace.execution_dirs import prunable_dirs

        register_execution_dir(
            ExecutionDir(
                name="test-unprunable-dir",
                purpose="Declared by a test without prunable.",
                versioned=False,
                products=False,
            )
        )
        try:
            assert resolve_execution_dir("test-unprunable-dir").prunable is False
            assert "test-unprunable-dir" not in {d.name for d in prunable_dirs()}
        finally:
            mod._REGISTRY.pop("test-unprunable-dir")
            mod._ORDER.remove("test-unprunable-dir")


class TestSourceDir:
    """arch-own-02b §2: ``source/`` is a declared, versioned, non-product peer."""

    def test_source_is_versioned_and_not_a_product(self):
        from molab.workspace.execution_dirs import SOURCE

        declared = resolve_execution_dir("source")

        assert declared is SOURCE
        assert declared.versioned is True
        assert declared.products is False

    def test_source_is_a_declared_name(self):
        from molab.workspace.execution_dirs import SOURCE

        assert SOURCE.name in execution_dir_names()

    def test_product_set_is_unchanged(self):
        from molab.workspace.execution_dirs import SOURCE

        assert SOURCE not in product_dirs()
        assert {d.name for d in product_dirs()} == {"out", "artifacts"}

    def test_scratch_set_is_unchanged(self):
        from molab.workspace.execution_dirs import SOURCE

        assert SOURCE not in scratch_dirs()
        assert {d.name for d in scratch_dirs()} == {"out", "work"}
