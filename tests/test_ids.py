"""Unit tests for the cross-layer ``molexp.ids`` primitive module.

``molexp.ids`` holds the pure id / slug / content-hash helpers promoted
out of ``molexp.workspace.utils`` (okf-01-01) so the ``molexp.knowledge``
bottom layer can cite them without importing workspace.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import molexp.ids as ids
from molexp.ids import (
    compute_content_hash,
    generate_asset_id,
    generate_id,
    slugify,
)


def test_slugify_lowercases_hyphenates_collapses() -> None:
    assert slugify("Hello   World") == "hello-world"
    assert slugify("My_Cool  Project!!") == "my-cool-project"
    assert slugify("a---b") == "a-b"


def test_slugify_truncates_to_max_len() -> None:
    assert slugify("a" * 100, max_len=10) == "a" * 10


def test_generate_id_is_8_hex_chars() -> None:
    value = generate_id()
    assert len(value) == 8
    int(value, 16)  # parses as hex


def test_generate_asset_id_is_valid_uuid() -> None:
    value = generate_asset_id()
    assert str(uuid.UUID(value)) == value


def test_compute_content_hash_file_prefix_and_stability(tmp_path: Path) -> None:
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"identical bytes")
    f2.write_bytes(b"identical bytes")
    h1 = compute_content_hash(f1)
    h2 = compute_content_hash(f2)
    assert h1.startswith("sha256:")
    assert h1 == h2  # stable for identical bytes


def test_compute_content_hash_directory_is_order_invariant(tmp_path: Path) -> None:
    d = tmp_path / "tree"
    (d / "x").mkdir(parents=True)
    (d / "x" / "1.txt").write_bytes(b"one")
    (d / "2.txt").write_bytes(b"two")
    first = compute_content_hash(d)
    # Recompute — must be deterministic regardless of walk order.
    assert compute_content_hash(d) == first
    assert first.startswith("sha256:")


def test_source_imports_no_workspace_or_upstream_layer() -> None:
    """The primitive must not import workspace or any upstream layer.

    Asserted at the AST level on the module's own source — the
    enforceable layer-independence invariant (a runtime ``sys.modules``
    probe is confounded by the eager ``molexp/__init__.py``). Mirrors
    ``tests/test_workspace/test_import_guard.py``.
    """
    forbidden = (
        "molexp.workspace",
        "molexp.workflow",
        "molexp.agent",
        "molexp.harness",
        "molexp.server",
        "molexp.cli",
        "molexp.plugins",
        "molexp.sweep",
    )
    source = Path(ids.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.startswith(forbidden)]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(forbidden):
            offenders.append(node.module)
    assert offenders == [], f"molexp.ids imports forbidden modules: {offenders}"


class TestHashChunking:
    def test_chunk_size_does_not_change_the_digest(self, tmp_path: Path) -> None:
        # The digest is over the byte stream, so read granularity is free to
        # change — this pins that, since the chunk size was raised for speed.
        import hashlib

        target = tmp_path / "f.bin"
        payload = bytes(range(256)) * 9000
        target.write_bytes(payload)

        assert compute_content_hash(target) == f"sha256:{hashlib.sha256(payload).hexdigest()}"

    def test_chunk_is_large_enough_to_not_be_syscall_bound(self) -> None:
        assert ids._HASH_CHUNK >= 1 << 20


class TestHashBytes:
    def test_matches_the_hash_of_the_same_bytes_on_disk(self, tmp_path: Path) -> None:
        payload = b"molecule" * 1000
        target = tmp_path / "f.bin"
        target.write_bytes(payload)

        assert ids.hash_bytes(payload) == compute_content_hash(target)

    def test_carries_the_algorithm_prefix(self) -> None:
        assert ids.hash_bytes(b"x").startswith("sha256:")


class TestHashCopyFusion:
    def test_digest_equals_a_separate_hash_of_the_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "src.bin"
        src.write_bytes(b"payload" * 5000)
        dst = tmp_path / "dst.bin"

        digest = ids.hash_copy(src, dst)

        ids.clear_hash_memo()
        assert digest == compute_content_hash(dst) == compute_content_hash(src)

    def test_creates_missing_parent_directories(self, tmp_path: Path) -> None:
        src = tmp_path / "src.bin"
        src.write_bytes(b"data")
        dst = tmp_path / "a" / "b" / "c.bin"

        ids.hash_copy(src, dst)

        assert dst.read_bytes() == b"data"


class TestHashMemoBounds:
    def test_memo_does_not_grow_without_limit(self, tmp_path: Path) -> None:
        ids.clear_hash_memo()
        for i in range(ids._HASH_MEMO_MAX + 50):
            target = tmp_path / f"f{i}.bin"
            target.write_bytes(str(i).encode())
            compute_content_hash(target)

        assert len(ids._hash_memo) <= ids._HASH_MEMO_MAX
        ids.clear_hash_memo()

    def test_clear_empties_the_memo(self, tmp_path: Path) -> None:
        target = tmp_path / "f.bin"
        target.write_bytes(b"x")
        compute_content_hash(target)
        ids.clear_hash_memo()
        assert len(ids._hash_memo) == 0
