"""Address parsing resolves registered molq identities, never raw SSH hosts."""

import pytest
from molq import MolqError

from molab.workspace import ComputeTarget, Workspace
from molab.workspace.fs_local import LocalFileSystem
from molab.workspace.fs_remote import RemoteFileSystem
from molab.workspace.target import (
    LocalTarget,
    RemoteTarget,
    TargetNeedsResolution,
    TargetNotFound,
    parse_target,
    resolve_target,
)


def test_local_addresses_and_builtin_target(tmp_path):
    target, fs = resolve_target(str(tmp_path))
    assert isinstance(target, LocalTarget) and isinstance(fs, LocalFileSystem)
    assert target.path == tmp_path
    ws = Workspace(tmp_path)
    target, fs = resolve_target("@local", ws)
    assert target.path == tmp_path and not target.is_remote
    with pytest.raises(TargetNeedsResolution):
        resolve_target("@missing")
    with pytest.raises(TargetNotFound):
        resolve_target("@missing", ws)


def test_registered_destination_address_and_workspace_reference(molq_destination, tmp_path):
    client, registry, cluster, root = molq_destination
    target = parse_target(f"{cluster}:{root}")
    assert isinstance(target, RemoteTarget)
    assert target.registry_id == registry
    assert target.cluster_id == client.cluster(cluster).definition()["id"]
    assert target.path == str(root)
    ws = Workspace(tmp_path / "workspace")
    ws.add_target(
        ComputeTarget(
            name="compute",
            registry_id=target.registry_id,
            cluster_id=target.cluster_id,
            scratch_root=str(root),
        )
    )
    resolved, fs = resolve_target("@compute", ws)
    assert resolved.cluster_id == target.cluster_id and isinstance(fs, RemoteFileSystem)
    with pytest.raises(MolqError) as error:
        parse_target("unregistered-ssh-host:/tmp")
    assert error.value.kind == "CLUSTER_NOT_FOUND"
