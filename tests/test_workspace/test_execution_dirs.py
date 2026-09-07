"""The Execution's directories are peers, and their meaning is data."""

from __future__ import annotations

import pytest

from molexp.workspace.execution_dirs import (
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
            from molexp.workspace import execution_dirs as mod

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
