"""``snapshot._normalize_ast`` — AST-normalized code hashing.

The content-addressed cache keys on a hash derived from AST-normalized task
source. Formatting/comments must be invisible to the hash, but decorators are
part of semantic identity — a behaviour-changing decorator (retry, units,
lru_cache, validation) MUST invalidate the hash, or the cache silently returns
stale/wrong results.
"""

from __future__ import annotations

from molab.workflow.snapshot import _normalize_ast


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


class TestHelperModuleIdentity:
    """A task that calls into a sibling helper module changes identity with it."""

    @staticmethod
    def _load(tmp_path, name) -> object:
        import importlib.util
        import sys

        sys.path.insert(0, str(tmp_path))
        try:
            spec = importlib.util.spec_from_file_location(name, tmp_path / f"{name}.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        finally:
            sys.path.remove(str(tmp_path))

    def test_editing_an_imported_helper_changes_the_code_hash(self, tmp_path):
        from molab.workflow.snapshot import TaskSnapshot

        (tmp_path / "helper.py").write_text("def stat():\n    return 1\n")
        (tmp_path / "wf_mod.py").write_text(
            "def task():\n    import helper\n\n    return helper.stat()\n"
        )
        before = TaskSnapshot.from_task_body("t", self._load(tmp_path, "wf_mod").task).code_hash
        (tmp_path / "helper.py").write_text("def stat():\n    return 2\n")
        after = TaskSnapshot.from_task_body("t", self._load(tmp_path, "wf_mod").task).code_hash
        assert before != after

    def test_a_task_with_no_local_import_keeps_its_ast_hash(self, tmp_path):
        from molab.workflow.snapshot import TaskSnapshot

        (tmp_path / "plain.py").write_text("import json\n\ndef task():\n    return json.dumps(1)\n")
        snap = TaskSnapshot.from_task_body("t", self._load(tmp_path, "plain").task)
        assert snap.code_hash == TaskSnapshot._hash_callable(
            self._load(tmp_path, "plain").task, "x", "t"
        )
