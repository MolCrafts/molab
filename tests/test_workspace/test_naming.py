"""Directory names are for people (``molab.workspace.naming``).

The naming law: a path segment says *what* something is, an entity's ``id``
says *which* one it is, and the two never swap roles. These tests pin the
derivations so a run directory keeps telling a reader the parameters it ran
at, and a UUID never leaks back into a path.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from molab.workspace import Experiment, Project, Run, Workspace
from molab.workspace.naming import (
    EXPERIMENT_CONTAINER,
    MAX_RUN_SLUG,
    PROJECT_CONTAINER,
    RUN_CONTAINER,
    disambiguate,
    entity_slug,
    execution_slug,
    parse_execution_seq,
    run_slug,
)

FALLBACK = "sha256:0012ed3b447885f7257ce5aae22eacd31fb58cb05798556806e40125863d0977"


class TestEntitySlug:
    def test_display_name_becomes_a_kebab_slug(self):
        assert entity_slug("PEO Tg", fallback="x") == "peo-tg"
        assert entity_slug("size_convergence", fallback="x") == "size-convergence"

    def test_unrenderable_name_falls_back_to_a_digest_not_a_uuid(self):
        slug = entity_slug("!!!", fallback=FALLBACK)
        assert slug == "0012ed3b"
        assert "-" not in slug


class TestRunSlug:
    def test_parameters_are_the_name(self):
        params = {"dp": 5, "n_chains": 200, "force_field": "gaff", "seed": 42}
        assert run_slug(params, fallback=FALLBACK) == "dp=5_force_field=gaff_n_chains=200_seed=42"

    def test_key_order_is_stable_regardless_of_insertion_order(self):
        forward = run_slug({"a": 1, "b": 2}, fallback=FALLBACK)
        reverse = run_slug({"b": 2, "a": 1}, fallback=FALLBACK)
        assert forward == reverse == "a=1_b=2"

    def test_no_parameters_falls_back_to_a_digest(self):
        assert run_slug({}, fallback=FALLBACK) == "0012ed3b"
        assert run_slug(None, fallback=FALLBACK) == "0012ed3b"

    def test_floats_and_bools_render_readably(self):
        slug = run_slug({"coul": 0.8333, "polar": True}, fallback=FALLBACK)
        assert slug == "coul=0.8333_polar=yes"

    def test_path_separators_never_survive_into_a_segment(self):
        slug = run_slug({"path": "a/b", "name": "x y"}, fallback=FALLBACK)
        assert "/" not in slug
        assert " " not in slug

    def test_overlong_name_is_truncated_and_digest_suffixed(self):
        params = {f"key{i:02d}": "value" for i in range(20)}
        slug = run_slug(params, fallback=FALLBACK)
        assert len(slug) <= MAX_RUN_SLUG
        assert slug.endswith("_0012ed3b")


class TestExecutionSlug:
    def test_attempts_are_numbered_and_sort_by_eye(self):
        assert [execution_slug(n) for n in (1, 2, 10)] == ["e01", "e02", "e10"]
        assert sorted(["e10", "e02", "e01"]) == ["e01", "e02", "e10"]

    def test_sequence_round_trips(self):
        assert parse_execution_seq(execution_slug(7)) == 7
        assert parse_execution_seq("out") is None

    def test_zero_is_rejected(self):
        with pytest.raises(ValueError, match="starts at 1"):
            execution_slug(0)


class TestDisambiguate:
    def test_free_slug_passes_through(self):
        assert disambiguate("dp=5", set()) == "dp=5"

    def test_taken_slug_gets_the_first_free_suffix(self):
        assert disambiguate("dp=5", {"dp=5"}) == "dp=5-2"
        assert disambiguate("dp=5", {"dp=5", "dp=5-2"}) == "dp=5-3"


class TestSectionNamesComeFromTheDeclaration:
    """A directory name is written down once, in its declaration.

    A second spelling is how a metrics file gets written where nothing looks
    for it — which is exactly what happened when the products directory was
    renamed in the artifact repository but not in the metrics WAL. Now that
    the name lives in ``execution_dirs``, the guard is that nobody re-types
    it: a module that says ``"artifacts"`` in code has forked the name again.

    Only modules that build paths *directly* are checked. A call site saying
    ``ctx.get_dir("work")`` is safe because ``get_dir`` resolves the name
    against the registry and raises on an undeclared one — a rename surfaces
    there immediately, rather than silently writing to a dead directory.
    """

    @staticmethod
    def _code_strings(path: Path) -> set[str]:
        """String literals in *path* that are not docstrings.

        Docstrings are excluded on purpose: ``get_dir("work")`` in prose is
        documentation, and prose is where these names *should* appear.
        """

        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstrings.add(id(body[0].value))
        return {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        }

    def test_no_writer_retypes_a_declared_directory_name(self):
        from molab.plugins.metrics import wal
        from molab.workspace import artifact_repository, execution_context
        from molab.workspace.execution_dirs import execution_dir_names

        names = execution_dir_names()
        for module in (artifact_repository, execution_context, wal):
            retyped = self._code_strings(Path(module.__file__)) & names
            assert not retyped, (
                f"{module.__name__} hard-codes {sorted(retyped)}; "
                "import the declaration from execution_dirs instead"
            )


class TestNamingHasNoRootFinder:
    def test_naming_defines_no_workspace_root(self) -> None:
        import molab.workspace.naming as naming

        assert not hasattr(naming, "workspace_root")
        assert "workspace_root" not in naming.__all__


class TestContainerNames:
    """Container directory names come from ``naming``."""

    def test_the_three_containers_are_the_plural_child_kinds(self) -> None:
        assert PROJECT_CONTAINER == "projects"
        assert EXPERIMENT_CONTAINER == "experiments"
        assert RUN_CONTAINER == "runs"

    def test_child_dirs_use_the_constants(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        assert Project.child_dir(ws, "x").parent.name == PROJECT_CONTAINER
        project = ws.add_project("p")
        assert Experiment.child_dir(project, "e").parent.name == EXPERIMENT_CONTAINER
        experiment = project.add_experiment("e")
        assert Run.child_dir(experiment, "r").parent.name == RUN_CONTAINER
