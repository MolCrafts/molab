"""The Execution's directories are peers, and their meaning is data."""

from __future__ import annotations

import pytest

from molab.workspace.execution_dirs import (
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


class TestTheTiers:
    def test_work_and_out_are_declared(self) -> None:
        names = execution_dir_names()
        assert {"work", "out"} <= names
        assert "artifacts" not in names

    def test_bulk_tiers_stay_out_of_history(self) -> None:
        assert OUT.versioned is False
        assert WORK.versioned is False

    def test_scratch_is_not_a_place_readers_look(self) -> None:
        assert WORK.products is False
        assert OUT.products is True


class TestPeerStatus:
    def test_no_directory_carries_a_rank(self) -> None:
        assert not hasattr(OUT, "priority")
        assert set(ExecutionDir.__dataclass_fields__) == {
            "name",
            "purpose",
            "versioned",
            "products",
            "prunable",
        }

    def test_every_directory_explains_itself(self) -> None:
        for directory in list_execution_dirs():
            assert directory.purpose.strip()


class TestQueryingReplacesHardCoding:
    def test_products_are_found_by_property_not_by_name(self) -> None:
        assert {d.name for d in product_dirs()} == {"out"}

    def test_scratch_is_found_by_property_not_by_name(self) -> None:
        assert {d.name for d in scratch_dirs()} == {"out", "work"}


class TestRegistrationIsOpen:
    def test_a_package_can_declare_the_directory_it_writes(self) -> None:
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

    def test_registering_twice_replaces_rather_than_raises(self) -> None:
        register_execution_dir(WORK)
        register_execution_dir(WORK)
        assert [d.name for d in list_execution_dirs()].count("work") == 1


class TestUndeclaredNamesAreRefused:
    def test_resolving_an_unknown_directory_raises(self) -> None:
        with pytest.raises(UnknownExecutionDirError) as excinfo:
            resolve_execution_dir("outputs")
        assert "out" in str(excinfo.value)


class TestPrunableDirs:
    def test_seeded_prunable_dirs_are_the_bulk_tiers(self) -> None:
        from molab.workspace.execution_dirs import prunable_dirs

        assert {d.name for d in prunable_dirs()} == {"out", "work", "jobs", "checkpoints"}

    def test_source_is_not_prunable(self) -> None:
        from molab.workspace.execution_dirs import SOURCE

        assert SOURCE.prunable is False

    def test_undeclared_prunability_defaults_to_kept(self) -> None:
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
    def test_source_is_versioned_and_not_a_product(self) -> None:
        from molab.workspace.execution_dirs import SOURCE

        declared = resolve_execution_dir("source")

        assert declared is SOURCE
        assert declared.versioned is True
        assert declared.products is False

    def test_source_is_a_declared_name(self) -> None:
        from molab.workspace.execution_dirs import SOURCE

        assert SOURCE.name in execution_dir_names()

    def test_product_set_is_unchanged(self) -> None:
        from molab.workspace.execution_dirs import SOURCE

        assert SOURCE not in product_dirs()
        assert {d.name for d in product_dirs()} == {"out"}

    def test_scratch_set_is_unchanged(self) -> None:
        from molab.workspace.execution_dirs import SOURCE

        assert SOURCE not in scratch_dirs()
        assert {d.name for d in scratch_dirs()} == {"out", "work"}
