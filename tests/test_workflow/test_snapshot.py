"""``snapshot._normalize_ast`` — AST-normalized code hashing.

The content-addressed cache keys on a hash derived from AST-normalized task
source. Formatting/comments must be invisible to the hash, but decorators are
part of semantic identity — a behaviour-changing decorator (retry, units,
lru_cache, validation) MUST invalidate the hash, or the cache silently returns
stale/wrong results.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from molab.workflow.snapshot import (
    TaskSnapshot,
    _dependency_entries,
    _normalize_ast,
    _stable_config_default,
)


def _load_module(directory: Path, name: str) -> object:
    """Import ``<directory>/<name>.py`` fresh, with *directory* importable meanwhile.

    No ``.pyc`` is written: the import system validates a cached one by whole-
    second mtime and size, so a rewrite within the same second that keeps the
    size (``= 1`` -> ``= 2``) would execute the stale bytecode.
    """
    sys.path.insert(0, str(directory))
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name, directory / f"{name}.py")
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.dont_write_bytecode = saved
        sys.path.remove(str(directory))


def _code_hash(directory: Path, source: str, *, attr: str = "task") -> str:
    """The code hash of ``attr`` in a freshly written and imported ``wf_mod.py``."""
    (directory / "wf_mod.py").write_text(source, encoding="utf-8")
    body = getattr(_load_module(directory, "wf_mod"), attr)
    return TaskSnapshot.from_task_body("t", body).code_hash


class TestNormalizeAst:
    def test_comments_and_whitespace_are_ignored(self) -> None:
        """Pure formatting / comment differences hash identically."""
        plain = "def f(x):\n    return x + 1\n"
        noisy = "def f(x):\n    # explanatory comment\n    return x  +  1\n"
        assert _normalize_ast(plain) == _normalize_ast(noisy)

    def test_adding_a_decorator_changes_the_normalized_ast(self) -> None:
        """A decorated body must differ from the undecorated one."""
        plain = "def f(x):\n    return x + 1\n"
        decorated = "@retry(3)\ndef f(x):\n    return x + 1\n"
        assert _normalize_ast(plain) != _normalize_ast(decorated)


class TestConfigIdentity:
    def test_two_paths_do_not_share_a_config_encoding(self) -> None:
        assert _stable_config_default(Path("/tmp/a")) != _stable_config_default(Path("/tmp/b"))


class TestHelperModuleIdentity:
    """A task that calls into a sibling helper module changes identity with it."""

    _load = staticmethod(_load_module)

    def test_editing_an_imported_helper_changes_the_code_hash(self, tmp_path):
        (tmp_path / "helper.py").write_text("def stat():\n    return 1\n")
        (tmp_path / "wf_mod.py").write_text(
            "def task():\n    import helper\n\n    return helper.stat()\n"
        )
        before = TaskSnapshot.from_task_body("t", self._load(tmp_path, "wf_mod").task).code_hash
        (tmp_path / "helper.py").write_text("def stat():\n    return 2\n")
        after = TaskSnapshot.from_task_body("t", self._load(tmp_path, "wf_mod").task).code_hash
        assert before != after

    def test_editing_a_relative_import_changes_the_code_hash(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "helper.py").write_text("def stat():\n    return 1\n")
        (pkg / "wf_mod.py").write_text(
            "def task():\n    from .helper import stat\n\n    return stat()\n"
        )
        before = TaskSnapshot.from_task_body("t", self._load(pkg, "wf_mod").task).code_hash
        (pkg / "helper.py").write_text("def stat():\n    return 2\n")
        after = TaskSnapshot.from_task_body("t", self._load(pkg, "wf_mod").task).code_hash
        assert before != after

    def test_a_task_with_no_local_import_keeps_its_ast_hash(self, tmp_path):
        (tmp_path / "plain.py").write_text("import json\n\ndef task():\n    return json.dumps(1)\n")
        snap = TaskSnapshot.from_task_body("t", self._load(tmp_path, "plain").task)
        assert snap.code_hash == TaskSnapshot._hash_callable(
            self._load(tmp_path, "plain").task, "x", "t"
        )


_HELPERS = """\
import json
from pathlib import Path

HELPER_VALUE = {value}
UNUSED_VALUE = {unused}
COUNTERS = {{}}


def helper():
    {helper_comment}return HELPER_VALUE{helper_body}


def unused_helper():
    return {unused}


def task(ctx):
    COUNTERS["task"] = COUNTERS.get("task", 0) + 1
    return {{"x": helper(), "p": Path(json.dumps(1))}}
"""


def _helpers(
    *, value: int = 1, unused: int = 1, helper_body: str = "", helper_comment: str = ""
) -> str:
    return _HELPERS.format(
        value=value, unused=unused, helper_body=helper_body, helper_comment=helper_comment
    )


class TestModuleDependencyIdentity:
    """The code hash covers the module-level helpers and constants a body reaches.

    ``task`` calls ``helper`` which reads ``HELPER_VALUE``; neither is in
    ``task``'s own source, yet both decide what ``task`` computes. Pre-fix,
    ``--resume`` re-used ``task``'s cached output after either was edited.
    """

    def test_editing_a_referenced_helper_body_changes_the_code_hash(self, tmp_path):
        before = _code_hash(tmp_path, _helpers())
        after = _code_hash(tmp_path, _helpers(helper_body=" + 1"))
        assert before != after

    def test_editing_a_referenced_constant_changes_the_code_hash(self, tmp_path):
        before = _code_hash(tmp_path, _helpers(value=1))
        after = _code_hash(tmp_path, _helpers(value=2))
        assert before != after

    def test_editing_an_unreferenced_helper_or_constant_keeps_the_code_hash(self, tmp_path):
        before = _code_hash(tmp_path, _helpers(unused=1))
        after = _code_hash(tmp_path, _helpers(unused=2))
        assert before == after

    def test_comments_and_formatting_in_a_helper_keep_the_code_hash(self, tmp_path):
        before = _code_hash(tmp_path, _helpers())
        after = _code_hash(tmp_path, _helpers(helper_comment="# a comment\n    \n    "))
        assert before == after

    def test_stdlib_globals_are_not_dependencies(self, tmp_path):
        (tmp_path / "wf_mod.py").write_text(_helpers(), encoding="utf-8")
        entries = _dependency_entries(_load_module(tmp_path, "wf_mod").task)
        assert [e.split(":")[0] for e in entries] == [
            "const COUNTERS",
            "const HELPER_VALUE",
            "def helper",
        ]

    def test_a_mutated_module_dict_keeps_the_code_hash(self, tmp_path):
        """A global is identified by the statement binding it, not its runtime value."""
        (tmp_path / "wf_mod.py").write_text(_helpers(), encoding="utf-8")
        mod = _load_module(tmp_path, "wf_mod")
        before = TaskSnapshot.from_task_body("t", mod.task).code_hash
        mod.task(None)
        assert mod.COUNTERS == {"task": 1}
        assert TaskSnapshot.from_task_body("t", mod.task).code_hash == before

    def test_a_helper_cycle_terminates(self, tmp_path):
        cyclic = (
            "def ping(n):\n    return pong(n - 1) if n else 0\n\n"
            "def pong(n):\n    return ping(n - 1) if n else {leaf}\n\n"
            "def task(ctx):\n    return ping(3)\n"
        )
        before = _code_hash(tmp_path, cyclic.format(leaf=0))
        after = _code_hash(tmp_path, cyclic.format(leaf=1))
        assert before != after

    def test_editing_a_referenced_class_changes_the_code_hash(self, tmp_path):
        source = (
            "class Settings:\n    scale = {scale}\n\n"
            "    def value(self):\n        return self.scale\n\n"
            "def task(ctx):\n    return Settings().value()\n"
        )
        before = _code_hash(tmp_path, source.format(scale=1))
        after = _code_hash(tmp_path, source.format(scale=2))
        assert before != after

    def test_a_task_class_reaches_its_own_methods(self, tmp_path):
        source = (
            "class Body:\n"
            "    def _helper(self):\n        return {leaf}\n\n"
            "    async def execute(self, ctx):\n        return self._helper()\n\n"
            "body = Body()\n"
        )
        before = _code_hash(tmp_path, source.format(leaf=1), attr="body")
        after = _code_hash(tmp_path, source.format(leaf=2), attr="body")
        assert before != after

    def test_a_global_without_a_binding_statement_hashes_by_value(self, tmp_path):
        source = 'globals()["DYN"] = {value}\n\ndef task(ctx):\n    return DYN\n'
        before = _code_hash(tmp_path, source.format(value=1))
        after = _code_hash(tmp_path, source.format(value=2))
        assert before != after
        (tmp_path / "wf_mod.py").write_text(source.format(value=3), encoding="utf-8")
        entries = _dependency_entries(_load_module(tmp_path, "wf_mod").task)
        assert entries == ["const DYN: val:3"]

    @pytest.mark.parametrize("decorated", [False, True])
    def test_helper_decorators_are_part_of_the_identity(self, tmp_path, decorated: bool):
        plain = "def helper():\n    return 1\n\ndef task(ctx):\n    return helper()\n"
        wrapped = "import functools\n\n@functools.cache\n" + plain
        before = _code_hash(tmp_path, plain)
        after = _code_hash(tmp_path, wrapped if decorated else plain)
        assert (before != after) is decorated
