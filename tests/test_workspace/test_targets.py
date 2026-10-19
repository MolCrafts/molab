"""Tests for the compute-target registry and the molq Transport bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workspace import ComputeTarget, Workspace
from molab.workspace.fs_local import LocalFileSystem
from molab.workspace.fs_remote import RemoteFileSystem
from molab.workspace.targets import to_filesystem


class TestComputeTargetValidation:
    """The ``_validate_axes`` model_validator on ``ComputeTarget``."""

    def test_scratch_root_is_required(self) -> None:
        with pytest.raises(ValueError, match="scratch_root"):
            ComputeTarget(name="x", scratch_root="")

    def test_incomplete_destination_rejected(self) -> None:
        with pytest.raises(ValueError, match="together"):
            ComputeTarget(name="x", scratch_root="/tmp", cluster_id="files")


class TestRegistry:
    """CRUD over ``WorkspaceMetadata.targets`` via the ``targets`` helpers."""

    def test_add_get_round_trips_through_workspace_json(self, tmp_path: Path) -> None:
        """A registered target survives a fresh ``Workspace`` load unchanged."""
        ws = Workspace(tmp_path)
        ws.materialize()
        ws.add_target(
            ComputeTarget(
                name="hpc",
                registry_id="registry",
                cluster_id="destination",
                scratch_root="/scratch/me",
            ),
        )

        ws2 = Workspace(tmp_path)  # fresh load
        t = ws2.get_target("hpc")
        assert t.registry_id == "registry"
        assert t.cluster_id == "destination"
        assert t.scratch_root == "/scratch/me"

    def test_add_duplicate_name_rejected(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path)
        ws.materialize()
        ws.add_target(ComputeTarget(name="a", scratch_root="/tmp"))
        with pytest.raises(ValueError, match="already exists"):
            ws.add_target(ComputeTarget(name="a", scratch_root="/other"))

    def test_remove_drops_named_target(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path)
        ws.materialize()
        ws.add_target(ComputeTarget(name="a", scratch_root="/tmp"))
        ws.add_target(ComputeTarget(name="b", scratch_root="/tmp"))
        ws.remove_target("a")
        assert [t.name for t in ws.list_targets()] == ["b"]

    def test_get_missing_raises(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path)
        ws.materialize()
        with pytest.raises(KeyError):
            ws.get_target("ghost")


def test_filesystem_uses_the_same_destination(molq_destination):
    _client, registry, cluster, root = molq_destination
    target = ComputeTarget(
        name="hpc", registry_id=registry, cluster_id=cluster, scratch_root=str(root)
    )
    fs = to_filesystem(target)
    assert isinstance(fs, RemoteFileSystem)
    fs.write_text(root / "file", "payload")
    assert fs.read_text(root / "file") == "payload"
    assert isinstance(
        to_filesystem(ComputeTarget(name="local", scratch_root=str(root))), LocalFileSystem
    )


def test_legacy_connection_fields_are_rejected():
    with pytest.raises(ValueError):
        ComputeTarget(name="old", scratch_root="/tmp", host="example")
