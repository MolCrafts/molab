"""The molab adapter consumes paginated public file APIs with an explicit scope."""

from molab.workspace.fs_remote import RemoteFileSystem


def test_adapter_lists_metadata_and_reads_batches(molq_destination):
    client, _, cluster, root = molq_destination
    (root / "some file").write_bytes(b"content")
    (root / "directory").mkdir()
    fs = RemoteFileSystem(client, cluster, str(root))
    entries = {entry.name: entry for entry in fs.scandir(root)}
    assert entries["some file"].is_file and entries["some file"].size == 7
    assert entries["directory"].is_dir
    result = fs.read_many([str(root / "some file"), str(root / "absent")])
    assert result[str(root / "some file")] == b"content"
    assert isinstance(result[str(root / "absent")], FileNotFoundError)


def test_adapter_splits_only_explicit_batch_capacity_errors(molq_destination):
    client, _, cluster, root = molq_destination
    paths = []
    for i in range(4):
        path = root / str(i)
        path.write_bytes(bytes([i]) * 200000)
        paths.append(str(path))
    fs = RemoteFileSystem(client, cluster, str(root))
    assert fs.read_many(paths) == {path: bytes([i]) * 200000 for i, path in enumerate(paths)}


def test_cached_run_and_execution_listing_batches_metadata(molq_destination, tmp_path, monkeypatch):
    from molab.workspace import Workspace
    from molab.workspace.fs_cached import CachedRemoteFileSystem
    from molab.workspace.scope import open_serve_root

    client, _, cluster, root = molq_destination
    local = Workspace(root)
    local.materialize()
    project = local.add_project("p")
    experiment = project.add_experiment("e")
    runs = [experiment.add_run(params={"seed": i}) for i in range(4)]
    for run in runs:
        with run.start() as context:
            context.mark_succeeded()
    fs = CachedRemoteFileSystem(
        RemoteFileSystem(client, cluster, str(project.resolve())), mirror_root=tmp_path / "mirror"
    )
    remote = open_serve_root(str(project.resolve()), fs=fs).list_experiments()[0]
    requested = []
    listed = []
    rpc = client.rpc

    def record(method: str, **params: object):
        if method == "files.read_many":
            requested.extend(params["paths"])
        if method == "files.list":
            listed.append(params["path"])
        return rpc(method, **params)

    monkeypatch.setattr(client, "rpc", record)
    remote_runs = remote.list_runs()
    assert {run.id for run in remote_runs} == {run.id for run in runs}
    assert set(requested) == {str(run.resolve() / "run.json") for run in runs}
    requested.clear()
    listed.clear()
    assert all(len(run.executions) == 1 for run in remote_runs)
    assert len(listed) == len(runs)
    assert len(requested) == len(runs)
    assert all(path.endswith("/execution.json") for path in requested)


def test_semantic_prefetch_batches_entity_metadata_without_payloads(
    molq_destination, tmp_path, monkeypatch
):
    from molab.workspace import Workspace
    from molab.workspace.fs_cached import CachedRemoteFileSystem, prefetch_workspace_indices

    client, _, cluster, root = molq_destination
    local = Workspace(root)
    local.materialize()
    for i in range(3):
        project = local.add_project(f"p-{i}")
        experiment = project.add_experiment("experiment")
        run = experiment.add_run(params={"seed": i})
        with run.start() as context:
            context.mark_succeeded()
    (root / "payload.bin").write_bytes(b"x" * 300000)
    requested = []
    rpc = client.rpc

    def record_rpc(method, **params: object):
        if method == "files.read_many":
            requested.append(params["paths"])
        return rpc(method, **params)

    monkeypatch.setattr(client, "rpc", record_rpc)
    fs = CachedRemoteFileSystem(
        RemoteFileSystem(client, cluster, str(root)), mirror_root=tmp_path / "mirror"
    )
    remote = Workspace(str(root), fs=fs)
    warnings = prefetch_workspace_indices(remote, max_workers=2)
    assert not warnings
    assert any(len(paths) == 3 for paths in requested)
    names = {path.rsplit("/", 1)[-1] for paths in requested for path in paths}
    assert names == {"project.json", "experiment.json", "run.json", "execution.json"}
    assert all(len(paths) <= 128 for paths in requested)
