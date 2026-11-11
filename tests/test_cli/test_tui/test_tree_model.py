"""Unit tests for ``molab.cli.tui.tree_model`` status folding."""

from __future__ import annotations

from molab.cli.tui.tree_model import TreeNode, _fold_status


def _leaf(name: str, status: str) -> TreeNode:
    return TreeNode(kind="run", node_id=("run", name), display_label=name, status=status)


class TestFoldStatus:
    """The experiment breadcrumb shows the most urgent child state."""

    def test_queued_run_outranks_succeeded_run(self) -> None:
        exp = TreeNode(kind="experiment", node_id=("experiment", "x"), display_label="x")
        exp.children = [_leaf("a", "succeeded"), _leaf("b", "queued")]

        assert _fold_status(exp) == "queued"

    def test_interrupted_run_outranks_succeeded_run(self) -> None:
        exp = TreeNode(kind="experiment", node_id=("experiment", "x"), display_label="x")
        exp.children = [_leaf("a", "succeeded"), _leaf("b", "interrupted")]

        assert _fold_status(exp) == "interrupted"
