"""Compute targets — LocalTarget, RemoteTarget, and target resolution.

Matches ``docs/en/guide/workspace-architecture.md``.

Demonstrates:

1. ``LocalTarget`` — execution on the local filesystem.
2. ``RemoteTarget`` — an address referencing a molq destination.
3. ``ComputeTarget`` — the persisted base (stored in workspace config).
4. ``resolve_compute_target(ws, name)`` — named-target resolution.
5. Target registration in workspace configuration.

Run directly::

    python examples/operations/remote_targets.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import molab as me
from molab.workspace.target import LocalTarget, RemoteTarget
from molab.workspace.targets import resolve_compute_target


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-targets-"))
    ws = me.Workspace(root, name="targets-demo")

    scratch = Path(tempfile.mkdtemp(prefix="molab-scratch-"))

    # ── 1. LocalTarget — the default for in-process execution ────────────
    local = LocalTarget(scratch_root=str(scratch))
    print(f"LocalTarget:    {local}")
    print(f"  is_remote:    {local.is_remote}")
    print(f"  scratch_root: {local.scratch_root}")

    # ── 2. RemoteTarget — molq owns the connection definition ────────────
    # Illustrative IDs only. For real destinations, use parse_target("hpc:/scratch/alice")
    # or `molab target add gpu-cluster --cluster hpc --scratch /scratch/alice`.
    remote = RemoteTarget(
        registry_id="example-registry", cluster_id="example-cluster", path="/scratch/alice"
    )
    print(f"RemoteTarget:   {remote}")
    print(f"  registry:     {remote.registry_id}")
    print(f"  cluster:      {remote.cluster_id}")
    print(f"  is_remote:    {remote.is_remote}")

    # ── 3. ComputeTarget — the persisted base stored in workspace.json ───
    from molab.workspace.models import ComputeTarget

    ct = ComputeTarget(
        name="gpu-cluster",
        registry_id=remote.registry_id,
        cluster_id=remote.cluster_id,
        scratch_root=remote.scratch_root,
    )
    print(f"\nComputeTarget(name='{ct.name}'):")
    print(f"  cluster:   {ct.cluster_id}")
    print(f"  is_remote: {ct.is_remote}")

    # ── 4. resolve_compute_target — resolve built-in "local" ────────────
    resolved = resolve_compute_target(ws, "local")
    print("\nresolve_compute_target(ws, 'local'):")
    print(f"  name:      {resolved.name}")
    print(f"  is_remote: {resolved.is_remote}")

    # ── 5. Register a target in workspace config ─────────────────────────
    # ComputeTargets are persisted in the workspace config; resolve by name
    # after adding them through the workspace's target API.
    ws.add_target(ct)
    print(f"\nRegistered target: {resolve_compute_target(ws, ct.name)}")


if __name__ == "__main__":
    main()
