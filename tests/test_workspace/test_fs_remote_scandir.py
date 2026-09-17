"""``RemoteFileSystem`` bulk ops: one round-trip each, parsed exactly.

Every one of these operations used to cost a round-trip per *entry*. The
assertions are therefore about the number of transport calls as much as the
values: a correct listing that takes 2N round-trips is the bug these replace.
"""

from __future__ import annotations

import base64
import io
import tarfile

import pytest
from molq.transport import CommandResult

from molab.workspace.fs_remote import RemoteFileSystem


def _printf_stream(records: list[tuple[str, str, int, float, str]]) -> str:
    """Base64 of a NUL-separated ``find -printf '%y\\t%Y\\t%s\\t%T@\\t%f\\0'`` stream."""
    raw = b"".join(
        f"{kind}\t{target}\t{size}\t{mtime}\t{name}\0".encode("utf-8", "surrogateescape")
        for kind, target, size, mtime, name in records
    )
    return base64.b64encode(raw).decode()


class ScriptedTransport:
    """Answers ``run`` from a queue of scripted results; records every command."""

    def __init__(self, *results: CommandResult) -> None:
        self.queued = list(results)
        self.commands: list[str] = []
        self.calls = 0

    def run(self, argv, *, cwd=None, env=None, input=None, timeout=None):
        self.calls += 1
        self.commands.append(argv[-1])
        if self.queued:
            return self.queued.pop(0)
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    # Per-path ops, used only by the portable fallback path.
    def __getattr__(self, name: str):
        raise AttributeError(name)


def _ok(stdout: str) -> CommandResult:
    return CommandResult(argv=("sh",), returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str, returncode: int = 1) -> CommandResult:
    return CommandResult(argv=("sh",), returncode=returncode, stdout="", stderr=stderr)


class TestScandirParsing:
    def test_one_round_trip_for_a_whole_listing(self) -> None:
        transport = ScriptedTransport(
            _ok(
                _printf_stream(
                    [
                        ("d", "d", 4096, 1700.0, "runs"),
                        ("f", "f", 12, 1701.5, "run.json"),
                    ]
                )
            )
        )
        entries = RemoteFileSystem(transport).scandir("/ws")

        assert transport.calls == 1, "a listing must cost exactly one round-trip"
        by_name = {e.name: e for e in entries}
        assert by_name["runs"].is_dir and by_name["runs"].size == 4096
        assert by_name["run.json"].is_file and by_name["run.json"].mtime == 1701.5

    def test_symlink_to_dir_reports_both_flags(self) -> None:
        transport = ScriptedTransport(_ok(_printf_stream([("l", "d", 7, 1.0, "link")])))
        entry = RemoteFileSystem(transport).scandir("/ws")[0]
        assert entry.is_symlink and entry.is_dir and not entry.is_file

    def test_dangling_and_looping_links_are_neither(self) -> None:
        transport = ScriptedTransport(
            _ok(_printf_stream([("l", "N", 0, 0.0, "dead"), ("l", "L", 0, 0.0, "loop")]))
        )
        entries = RemoteFileSystem(transport).scandir("/ws")
        assert all(not e.is_dir and not e.is_file and e.is_symlink for e in entries)

    def test_names_with_spaces_survive(self) -> None:
        transport = ScriptedTransport(
            _ok(_printf_stream([("f", "f", 1, 1.0, "my file (copy).txt")]))
        )
        assert RemoteFileSystem(transport).scandir("/ws")[0].name == "my file (copy).txt"

    def test_non_utf8_name_round_trips(self) -> None:
        raw = b"f\tf\t1\t1.0\t" + b"caf\xe9.txt" + b"\0"
        transport = ScriptedTransport(_ok(base64.b64encode(raw).decode()))
        entry = RemoteFileSystem(transport).scandir("/ws")[0]
        assert entry.name.startswith("caf")

    def test_empty_listing_is_empty_list(self) -> None:
        assert RemoteFileSystem(ScriptedTransport(_ok(""))).scandir("/ws") == []

    def test_command_shape_is_a_single_maxdepth_find(self) -> None:
        transport = ScriptedTransport(_ok(""))
        RemoteFileSystem(transport).scandir("/ws/runs")
        command = transport.commands[0]
        assert "find" in command and "-maxdepth 1" in command and "-mindepth 1" in command
        assert "base64" in command


class TestScandirErrors:
    def test_missing_directory_raises_file_not_found(self) -> None:
        transport = ScriptedTransport(_fail("find: '/nope': No such file or directory"))
        with pytest.raises(FileNotFoundError):
            RemoteFileSystem(transport).scandir("/nope")

    def test_file_path_raises_not_a_directory(self) -> None:
        transport = ScriptedTransport(_fail("find: '/ws/a.txt': Not a directory"))
        with pytest.raises(NotADirectoryError):
            RemoteFileSystem(transport).scandir("/ws/a.txt")


class TestBsdFallback:
    def test_unknown_printf_switches_to_portable_listing_once(self) -> None:
        class _Portable(ScriptedTransport):
            def __init__(self) -> None:
                super().__init__(_fail("find: -printf: unknown primary or operator"))
                self.listdirs = 0

            def is_dir(self, path: str) -> bool:
                return path.endswith("ws")

            def exists(self, path: str) -> bool:
                return True

            def listdir(self, path: str) -> list[str]:
                self.listdirs += 1
                return ["a.txt"]

            def stat(self, path: str) -> dict[str, object]:
                return {"size": 3, "mtime": 9.0, "is_dir": False, "is_file": True}

        transport = _Portable()
        fs = RemoteFileSystem(transport)

        first = fs.scandir("/ws")
        assert first[0].name == "a.txt" and first[0].is_file
        assert fs._gnu_find is False, "the probe result must be remembered"

        fs.scandir("/ws")
        assert transport.calls == 1, "a host without GNU find is probed only once"


class TestReadRange:
    def test_returns_the_decoded_slice(self) -> None:
        transport = ScriptedTransport(_ok(base64.b64encode(b"cde").decode()))
        assert RemoteFileSystem(transport).read_range("/ws/f.txt", 2, 3) == b"cde"

    def test_command_bounds_the_transfer_at_the_source(self) -> None:
        transport = ScriptedTransport(_ok(""))
        RemoteFileSystem(transport).read_range("/ws/big.log", 100, 64)
        command = transport.commands[0]
        # tail -c is 1-based, so offset 100 becomes +101.
        assert "tail -c +101" in command and "head -c 64" in command

    def test_zero_length_does_no_round_trip(self) -> None:
        transport = ScriptedTransport()
        assert RemoteFileSystem(transport).read_range("/ws/f", 0, 0) == b""
        assert transport.calls == 0

    def test_negative_offset_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            RemoteFileSystem(ScriptedTransport()).read_range("/ws/f", -1, 5)

    def test_directory_raises(self) -> None:
        transport = ScriptedTransport(_fail("tail: error reading 'x': Is a directory"))
        with pytest.raises(IsADirectoryError):
            RemoteFileSystem(transport).read_range("/ws/dir", 0, 5)


class TestRglobRoundTrips:
    def test_costs_one_round_trip_per_directory_not_per_entry(self) -> None:
        # /ws -> [sub(dir), a.txt]; /ws/sub -> [b.txt]
        transport = ScriptedTransport(
            _ok(_printf_stream([("d", "d", 0, 1.0, "sub"), ("f", "f", 1, 1.0, "a.txt")])),
            _ok(_printf_stream([("f", "f", 1, 1.0, "b.txt")])),
        )
        found = sorted(RemoteFileSystem(transport).rglob("/ws", "*.txt"))

        assert found == ["/ws/a.txt", "/ws/sub/b.txt"]
        assert transport.calls == 2, (
            "two directories = two round-trips; the old body also paid one is_dir per entry"
        )


class TestWalkEntries:
    def test_one_round_trip_returns_the_whole_tree(self) -> None:
        raw = b"".join(
            f"{k}\t{t}\t{s}\t{m}\t{p}\0".encode()
            for k, t, s, m, p in [
                ("d", "d", 0, 1.0, "/ws"),
                ("d", "d", 0, 1.0, "/ws/projects"),
                ("f", "f", 10, 2.0, "/ws/workspace.json"),
                ("f", "f", 20, 3.0, "/ws/projects/p.json"),
            ]
        )
        transport = ScriptedTransport(_ok(base64.b64encode(raw).decode()))

        tree = RemoteFileSystem(transport).walk_entries("/ws", max_depth=3, prune=["executions"])

        assert transport.calls == 1
        assert {e.name for e in tree["/ws"]} == {"projects", "workspace.json"}
        assert {e.name for e in tree["/ws/projects"]} == {"p.json"}

    def test_prune_names_are_passed_to_find(self) -> None:
        transport = ScriptedTransport(_ok(""))
        RemoteFileSystem(transport).walk_entries("/ws", max_depth=7, prune=["executions", "logs"])
        command = transport.commands[0]
        assert "-prune" in command and "executions" in command and "logs" in command

    def test_failure_returns_empty_rather_than_raising(self) -> None:
        transport = ScriptedTransport(_fail("boom"))
        assert RemoteFileSystem(transport).walk_entries("/ws", max_depth=2) == {}


class TestFetchFiles:
    def test_one_round_trip_returns_every_small_file(self) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for name, body in [("./run.json", b'{"a":1}'), ("./x/meta.yaml", b"type: x")]:
                info = tarfile.TarInfo(name)
                info.size = len(body)
                tf.addfile(info, io.BytesIO(body))
        transport = ScriptedTransport(_ok(base64.b64encode(buf.getvalue()).decode()))

        files = RemoteFileSystem(transport).fetch_files(
            "/ws", names=["run.json", "meta.yaml"], max_bytes=1_000_000
        )

        assert transport.calls == 1, "the whole metadata load is one round-trip"
        assert files["/ws/run.json"] == b'{"a":1}'
        assert files["/ws/x/meta.yaml"] == b"type: x"

    def test_size_ceiling_is_applied_at_the_source(self) -> None:
        transport = ScriptedTransport(_ok(""))
        RemoteFileSystem(transport).fetch_files("/ws", names=["run.json"], max_bytes=4096)
        assert "-size -4096c" in transport.commands[0]

    def test_no_names_does_no_round_trip(self) -> None:
        transport = ScriptedTransport()
        assert RemoteFileSystem(transport).fetch_files("/ws", names=[], max_bytes=10) == {}
        assert transport.calls == 0

    def test_corrupt_stream_returns_empty_rather_than_raising(self) -> None:
        transport = ScriptedTransport(_ok(base64.b64encode(b"not a tar").decode()))
        assert RemoteFileSystem(transport).fetch_files("/ws", names=["x"], max_bytes=10) == {}
