"""Filesystem-class detection and the policies it selects."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.fs import profile as profile_mod
from molab.fs.profile import (
    LOCAL_FAST_PROFILE,
    NETWORK_LOCAL_PROFILE,
    REMOTE_SSH_PROFILE,
    FsKind,
    detect_fs_profile,
    profile_for_kind,
    reset_profile_cache,
)

_MOUNTS = """\
/dev/sda1 / xfs rw,relatime 0 0
storage:/vol/home /home nfs4 rw,relatime 0 0
10.0.0.1@o2ib:/lustre /scratch/lustre lustre rw 0 0
tmpfs /tmp tmpfs rw 0 0
"""


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(profile_mod.ENV_OVERRIDE, raising=False)
    reset_profile_cache()
    yield
    reset_profile_cache()


@pytest.fixture
def mounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    table = tmp_path / "mounts"
    table.write_text(_MOUNTS)
    monkeypatch.setattr(profile_mod, "_MOUNTS_PATH", str(table))
    reset_profile_cache()


class TestDetection:
    def test_local_disk_is_local_fast(self, mounts: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(profile_mod.os.path, "realpath", lambda _path: "/var/data/ws")
        assert detect_fs_profile("/var/data/ws").kind is FsKind.LOCAL_FAST

    def test_nfs_mount_is_network_local(
        self, mounts: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(profile_mod.os.path, "realpath", lambda _path: "/home/alice/lab")
        profile = detect_fs_profile("/home/alice/lab")
        assert profile.kind is FsKind.NETWORK_LOCAL
        assert profile.fstype == "nfs4"

    def test_lustre_mount_is_network_local(
        self, mounts: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(profile_mod.os.path, "realpath", lambda _path: "/scratch/lustre/proj")
        assert detect_fs_profile("/scratch/lustre/proj").fstype == "lustre"

    def test_longest_mount_point_wins(self, mounts: None, monkeypatch: pytest.MonkeyPatch) -> None:
        # /scratch/lustre/... must not be attributed to the "/" xfs row.
        monkeypatch.setattr(profile_mod.os.path, "realpath", lambda _path: "/scratch/lustre/x/y")
        assert detect_fs_profile("/scratch/lustre/x/y").kind is FsKind.NETWORK_LOCAL

    def test_unreadable_mount_table_falls_back_to_local_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(profile_mod, "_MOUNTS_PATH", "/definitely/not/here")
        reset_profile_cache()
        assert detect_fs_profile("/anywhere").kind is FsKind.LOCAL_FAST

    def test_result_is_cached_per_path(self, mounts: None, monkeypatch: pytest.MonkeyPatch) -> None:
        reads = {"n": 0}
        real = profile_mod._read_mounts

        def counted():
            reads["n"] += 1
            return real()

        monkeypatch.setattr(profile_mod, "_read_mounts", counted)
        detect_fs_profile("/home/x")
        detect_fs_profile("/home/x")
        assert reads["n"] <= 1


class TestEnvOverride:
    def test_override_forces_a_kind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(profile_mod.ENV_OVERRIDE, "network-local")
        assert detect_fs_profile("/anything").kind is FsKind.NETWORK_LOCAL

    def test_unknown_override_falls_through_to_detection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(profile_mod.ENV_OVERRIDE, "not-a-kind")
        assert detect_fs_profile("/anything").kind in set(FsKind)


class TestPolicyTable:
    def test_local_fast_keeps_flock_and_wal(self) -> None:
        assert LOCAL_FAST_PROFILE.locks == "flock"
        assert LOCAL_FAST_PROFILE.sqlite_journal == "WAL"

    def test_network_local_avoids_flock_and_wal(self) -> None:
        # Lustre without -o flock returns ENOSYS, and WAL's -shm file is
        # unsafe over NFS — both are silent-corruption paths, not slowdowns.
        assert NETWORK_LOCAL_PROFILE.locks == "o_excl"
        assert NETWORK_LOCAL_PROFILE.sqlite_journal == "DELETE"
        assert NETWORK_LOCAL_PROFILE.prefetch_workers > 1
        assert NETWORK_LOCAL_PROFILE.scandir_with_stat is False

    def test_remote_ssh_disables_local_locking(self) -> None:
        assert REMOTE_SSH_PROFILE.locks == "none"

    def test_profile_for_kind_round_trips(self) -> None:
        for kind in FsKind:
            assert profile_for_kind(kind).kind is kind
