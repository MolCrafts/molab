"""``CachedRemoteFileSystem`` measured in round-trips, not return values.

Every assertion here counts calls into the inner filesystem. That is the
entire point of the cache: a correct answer that cost an SSH round-trip is
the bug. The counting fake below is deliberately dumb — it records what was
asked of it and nothing else, so a regression shows up as a number, not as a
subtle behavioural difference.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from molexp.fs import DirEntry, StatResult
from molexp.workspace.fs_cached import (
    CachedRemoteFileSystem,
    prefetch_workspace_indices,
)

ROOT = "/scratch/me/ws"


class CountingRemote:
    """In-memory remote whose every call is counted.

    Mirrors the shape of ``RemoteFileSystem``: ``scandir`` answers a whole
    listing with metadata in one call, and the per-path ops each cost one.
    """

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.calls: Counter[str] = Counter()
        self.bulk_enabled = False

    # ── path math (free, never counted — no I/O) ────────────────────────

    def join(self, *parts: object) -> str:
        return "/".join(str(p).rstrip("/") for p in parts)

    def dirname(self, path: object) -> str:
        return str(path).rsplit("/", 1)[0]

    def basename(self, path: object) -> str:
        return str(path).rsplit("/", 1)[-1]

    def resolve(self, path: object) -> str:
        return str(path)

    def is_absolute(self, path: object) -> bool:
        return str(path).startswith("/")

    # ── per-path I/O (each one a round-trip) ────────────────────────────

    def _children(self, path: str) -> set[str]:
        prefix = path.rstrip("/") + "/"
        return {k[len(prefix) :].split("/", 1)[0] for k in self.files if k.startswith(prefix)}

    def _is_dir(self, path: str) -> bool:
        return bool(self._children(str(path))) and str(path) not in self.files

    def exists(self, path: object) -> bool:
        self.calls["exists"] += 1
        return str(path) in self.files or self._is_dir(str(path))

    def is_dir(self, path: object) -> bool:
        self.calls["is_dir"] += 1
        return self._is_dir(str(path))

    def is_file(self, path: object) -> bool:
        self.calls["is_file"] += 1
        return str(path) in self.files

    def listdir(self, path: object) -> list[str]:
        self.calls["listdir"] += 1
        return sorted(self._children(str(path)))

    def scandir(self, path: object, *, with_stat: bool = True) -> list[DirEntry]:
        self.calls["scandir"] += 1
        target = str(path)
        out: list[DirEntry] = []
        for name in sorted(self._children(target)):
            full = self.join(target, name)
            is_file = full in self.files
            out.append(
                DirEntry(
                    name=name,
                    is_dir=not is_file,
                    is_file=is_file,
                    size=len(self.files.get(full, b"")),
                    mtime=1700.0,
                )
            )
        return out

    def stat(self, path: object) -> StatResult:
        self.calls["stat"] += 1
        key = str(path)
        if key in self.files:
            return StatResult(size=len(self.files[key]), mtime=1700.0, is_dir=False, is_file=True)
        if self._is_dir(key):
            return StatResult(size=0, mtime=1700.0, is_dir=True, is_file=False)
        raise FileNotFoundError(key)

    def read_bytes(self, path: object) -> bytes:
        self.calls["read_bytes"] += 1
        key = str(path)
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]

    def read_text(self, path: object, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding)

    def read_range(self, path: object, offset: int, length: int) -> bytes:
        self.calls["read_range"] += 1
        return self.read_bytes(path)[offset : offset + length]

    # ── bulk accelerators (opt-in, mirroring RemoteFileSystem) ──────────

    def walk_entries(self, root: object, *, max_depth: int, prune=()) -> dict[str, list[DirEntry]]:
        if not self.bulk_enabled:
            raise AttributeError("walk_entries")
        self.calls["walk_entries"] += 1
        out: dict[str, list[DirEntry]] = {}
        seen = {str(root)}
        for key in self.files:
            parts = key[len(str(root)) :].strip("/").split("/")
            if any(p in prune for p in parts):
                continue
            cur = str(root)
            for part in parts:
                seen.add(cur)
                out.setdefault(cur, [])
                cur = self.join(cur, part)
        for directory in seen:
            out[directory] = self.scandir(directory)
            self.calls["scandir"] -= 1  # the walk is one trip, not one per dir
        return out

    def fetch_files(self, root: object, *, names, max_bytes: int, prune=()) -> dict[str, bytes]:
        if not self.bulk_enabled:
            raise AttributeError("fetch_files")
        self.calls["fetch_files"] += 1
        return {
            k: v
            for k, v in self.files.items()
            if self.basename(k) in names
            and len(v) <= max_bytes
            and not any(p in prune for p in k.split("/"))
        }

    # ── unused by these tests ───────────────────────────────────────────

    def mkdir(self, path: object, *, parents: bool = True, exist_ok: bool = True) -> None:
        return None

    def glob(self, path: object, pattern: str) -> list[str]:
        return []

    def rglob(self, path: object, pattern: str) -> list[str]:
        return []


def _seed(fs: CountingRemote, *, projects: int, experiments: int, runs: int) -> None:
    """Write a ``projects/experiments/runs`` tree with per-run metadata."""
    fs.files[f"{ROOT}/workspace.json"] = b'{"id":"ws"}'
    for p in range(projects):
        pd = f"{ROOT}/projects/p{p}"
        fs.files[f"{pd}/project.json"] = b'{"id":"p"}'
        fs.files[f"{pd}/meta.yaml"] = b"type: workspace.project\n"
        for e in range(experiments):
            ed = f"{pd}/experiments/e{e}"
            fs.files[f"{ed}/experiment.json"] = b'{"id":"e"}'
            fs.files[f"{ed}/meta.yaml"] = b"type: workspace.experiment\n"
            for r in range(runs):
                rd = f"{ed}/runs/run-r{r}"
                fs.files[f"{rd}/run.json"] = b'{"id":"r"}'
                fs.files[f"{rd}/_ops/run.json"] = b'{"status":"succeeded"}'
                fs.files[f"{rd}/assets.json"] = b'{"assets":[]}'
                fs.files[f"{rd}/meta.yaml"] = b"type: workspace.run\n"
                # Machine output: must never be walked or fetched.
                fs.files[f"{rd}/executions/exec-1/stdout.log"] = b"x" * 4096


@pytest.fixture
def remote() -> CountingRemote:
    fs = CountingRemote()
    _seed(fs, projects=5, experiments=4, runs=10)
    return fs


def _cached(remote: CountingRemote, tmp_path: Path, **kw: object) -> CachedRemoteFileSystem:
    return CachedRemoteFileSystem(remote, mirror_root=tmp_path / "mirror", **kw)


class TestScandirPinsChildren:
    @pytest.mark.unit
    def test_one_scandir_answers_every_child_stat_for_free(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """The multiplier that makes a remote tree loadable at all."""
        cached = _cached(remote, tmp_path)
        runs_dir = f"{ROOT}/projects/p0/experiments/e0/runs"
        entries = cached.scandir(runs_dir)
        assert len(entries) == 10
        remote.calls.clear()

        for entry in entries:
            child = f"{runs_dir}/{entry.name}"
            assert cached.is_dir(child) is True
            assert cached.exists(child) is True
            assert cached.stat(child).is_dir is True

        assert sum(remote.calls.values()) == 0, (
            f"child metadata must come from the listing, got {dict(remote.calls)}"
        )

    @pytest.mark.unit
    def test_listdir_reuses_the_pinned_listing(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        cached = _cached(remote, tmp_path)
        runs_dir = f"{ROOT}/projects/p0/experiments/e0/runs"
        first = cached.listdir(runs_dir)
        remote.calls.clear()

        assert cached.listdir(runs_dir) == first
        assert cached.scandir(runs_dir) != []
        assert sum(remote.calls.values()) == 0

    @pytest.mark.unit
    def test_read_bytes_after_scandir_costs_one_round_trip(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """Size/mtime came from the listing, so the extra ``stat`` is gone."""
        cached = _cached(remote, tmp_path)
        run_dir = f"{ROOT}/projects/p0/experiments/e0/runs/run-r0"
        cached.scandir(run_dir)
        remote.calls.clear()

        assert cached.read_bytes(f"{run_dir}/run.json") == b'{"id":"r"}'

        assert remote.calls["read_bytes"] == 1
        assert remote.calls["stat"] == 0, "the listing already carried size+mtime"
        assert sum(remote.calls.values()) == 1


class TestMirrorBudget:
    @pytest.mark.unit
    def test_oversized_file_is_returned_but_never_mirrored(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        remote.files[f"{ROOT}/big.bin"] = b"y" * 4096
        cached = _cached(remote, tmp_path, mirror_max_file_bytes=1024)

        assert cached.read_bytes(f"{ROOT}/big.bin") == b"y" * 4096
        assert not (tmp_path / "mirror" / "files" / "scratch/me/ws/big.bin").exists()

    @pytest.mark.unit
    def test_lru_eviction_frees_bytes_but_keeps_metadata(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """An evicted file still answers ``stat`` without SSH — only bytes go."""
        for i in range(4):
            remote.files[f"{ROOT}/log{i}.txt"] = b"z" * 1000
        cached = _cached(remote, tmp_path, mirror_budget_bytes=2500)

        for i in range(4):
            cached.read_bytes(f"{ROOT}/log{i}.txt")
            time.sleep(0.001)  # distinct last_used ordering

        mirrored = [k for k, e in cached._index.items() if e.mirrored]
        assert len(mirrored) <= 3, f"budget not enforced: {mirrored}"
        assert f"{ROOT}/log0.txt" not in mirrored, "LRU must evict the oldest first"

        remote.calls.clear()
        assert cached.stat(f"{ROOT}/log0.txt").size == 1000
        assert sum(remote.calls.values()) == 0, "evicted bytes must not cost metadata"

    @pytest.mark.unit
    def test_navigation_metadata_is_never_evicted(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """Evicting the tree to cache a log would undo the whole point."""
        cached = _cached(remote, tmp_path, mirror_budget_bytes=2000)
        run_dir = f"{ROOT}/projects/p0/experiments/e0/runs/run-r0"
        cached.read_bytes(f"{run_dir}/run.json")
        cached.read_bytes(f"{run_dir}/meta.yaml")

        for i in range(5):
            remote.files[f"{ROOT}/log{i}.txt"] = b"z" * 900
            cached.read_bytes(f"{ROOT}/log{i}.txt")

        assert cached._index[f"{run_dir}/run.json"].mirrored is True
        assert cached._index[f"{run_dir}/meta.yaml"].mirrored is True


class TestReadRange:
    @pytest.mark.unit
    def test_range_served_from_mirror_when_present(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        remote.files[f"{ROOT}/log.txt"] = b"0123456789"
        cached = _cached(remote, tmp_path)
        cached.read_bytes(f"{ROOT}/log.txt")
        remote.calls.clear()

        assert cached.read_range(f"{ROOT}/log.txt", 2, 4) == b"2345"
        assert sum(remote.calls.values()) == 0

    @pytest.mark.unit
    def test_range_on_unmirrored_file_forwards_without_mirroring(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """A slice must never be stored under the whole file's key."""
        remote.files[f"{ROOT}/huge.bin"] = b"abcdefghij"
        cached = _cached(remote, tmp_path)

        assert cached.read_range(f"{ROOT}/huge.bin", 0, 3) == b"abc"

        assert remote.calls["read_range"] == 1
        assert not (tmp_path / "mirror" / "files" / "scratch/me/ws/huge.bin").exists()


class TestSidecarWriteAmplification:
    @pytest.mark.unit
    def test_bulk_walk_does_not_rewrite_the_sidecar_per_record(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """1000 records used to mean 1000 full rewrites — O(records²) bytes."""
        cached = _cached(remote, tmp_path)
        writes = 0
        original = cached._write_sidecar

        def counting_write() -> None:
            nonlocal writes
            writes += 1
            original()

        cached._write_sidecar = counting_write  # type: ignore[method-assign]

        for i in range(1000):
            cached._record(f"{ROOT}/f{i}.json", kind="file", size=10, mtime=1700.0)
        cached.flush()

        assert writes <= 3, f"sidecar written {writes} times for 1000 records"
        assert cached._sidecar.exists()

    @pytest.mark.unit
    def test_flush_persists_every_pending_record(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """Debouncing may delay a write; it must never lose one."""
        cached = _cached(remote, tmp_path)
        for i in range(50):
            cached._record(f"{ROOT}/f{i}.json", kind="file", size=10, mtime=1700.0)
        cached.flush()

        reopened = _cached(remote, tmp_path)
        assert len(reopened.cached_paths()) >= 50


class TestRevalidateBefore:
    @pytest.mark.unit
    def test_entries_from_a_previous_process_revalidate_once_then_pin(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """One CLI invocation must see fresh data without paying per call."""
        first = _cached(remote, tmp_path)
        first.read_bytes(f"{ROOT}/workspace.json")
        first.flush()

        second = _cached(remote, tmp_path, revalidate_before=time.time())
        remote.calls.clear()
        second.read_bytes(f"{ROOT}/workspace.json")
        after_first = sum(remote.calls.values())
        assert after_first >= 1, "a stale entry must be re-read once"

        remote.calls.clear()
        second.read_bytes(f"{ROOT}/workspace.json")
        assert sum(remote.calls.values()) == 0, "and then be pinned for the process"


class TestBulkPrefetch:
    @pytest.mark.unit
    def test_bulk_path_warms_the_tree_in_two_round_trips(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """5x4x10 = 200 runs; the cost must not scale with that number."""
        remote.bulk_enabled = True
        cached = _cached(remote, tmp_path)
        ws = SimpleNamespace(root=ROOT, _fs=cached)

        warnings = prefetch_workspace_indices(ws)
        assert warnings == []

        assert remote.calls["walk_entries"] == 1
        assert remote.calls["fetch_files"] == 1
        assert sum(remote.calls.values()) == 2, (
            f"bulk prefetch must be two round-trips, got {dict(remote.calls)}"
        )

    @pytest.mark.unit
    def test_warm_tree_walk_touches_the_remote_zero_times(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """What the CLI/UI actually does after a prefetch."""
        remote.bulk_enabled = True
        cached = _cached(remote, tmp_path)
        prefetch_workspace_indices(SimpleNamespace(root=ROOT, _fs=cached))
        remote.calls.clear()

        for project in cached.listdir(f"{ROOT}/projects"):
            pd = f"{ROOT}/projects/{project}"
            assert cached.read_bytes(f"{pd}/project.json")
            for exp in cached.listdir(f"{pd}/experiments"):
                ed = f"{pd}/experiments/{exp}"
                assert cached.read_bytes(f"{ed}/experiment.json")
                for run in cached.listdir(f"{ed}/runs"):
                    rd = f"{ed}/runs/{run}"
                    assert cached.is_dir(rd)
                    assert cached.read_bytes(f"{rd}/run.json")
                    assert cached.read_bytes(f"{rd}/_ops/run.json")
                    assert cached.read_bytes(f"{rd}/assets.json")

        assert sum(remote.calls.values()) == 0, (
            f"a warm walk of 200 runs must be local, got {dict(remote.calls)}"
        )

    @pytest.mark.unit
    def test_bulk_prefetch_skips_machine_output(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """``executions/`` is where the bytes are; the tree must not descend in.

        ``find -prune`` still *lists* the pruned directory as a child of its
        parent — that entry is wanted, since it makes ``is_dir(executions)``
        free. What must never happen is descending into it or fetching the
        logs inside, which is where a run's bytes actually are.
        """
        remote.bulk_enabled = True
        cached = _cached(remote, tmp_path)
        prefetch_workspace_indices(SimpleNamespace(root=ROOT, _fs=cached))

        paths = cached.cached_paths()
        below = [k for k in paths if "/executions/" in k]
        assert below == [], f"pruned subtree was descended into: {below[:3]}"
        assert not any(k.endswith("stdout.log") for k in paths), "log bytes must not be prefetched"
        assert any(k.endswith("/executions") for k in paths), (
            "the pruned dir itself is still a cheap, useful entry"
        )

    @pytest.mark.unit
    def test_falls_back_to_the_per_level_walk_without_accelerators(
        self, remote: CountingRemote, tmp_path: Path
    ) -> None:
        """A host without GNU find still gets a warm tree, just not in two trips."""
        remote.bulk_enabled = False
        cached = _cached(remote, tmp_path)

        warnings = prefetch_workspace_indices(SimpleNamespace(root=ROOT, _fs=cached))

        assert warnings == []
        assert remote.calls["walk_entries"] == 0
        assert sum(remote.calls.values()) > 2
        assert any(k.endswith("run.json") for k in cached.cached_paths())
