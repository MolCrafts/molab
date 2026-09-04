"""RED tests for ``molexp.harness.plan.task_board`` — model + pure transitions.

Pins the frozen ``TaskBoard`` state model (``BoardTask`` / ``FeasibilityAnnotation``
/ enums) and its module-level pure transitions. Each transition
(``place_task`` / ``set_task_status`` / ``annotate_feasibility`` / ``remove_task``)
returns a NEW board with ``version`` incremented and MUST NOT mutate its input.
The board carries only ``version`` + ``tasks`` — no timestamps, no history.

Function-level unit tests only. The production subpackage
``molexp.harness.plan`` does not exist yet: a ``ModuleNotFoundError`` at import
time is the valid RED signal.
"""

from __future__ import annotations

import pytest

from molexp.harness.plan import (
    BoardTask,
    Difficulty,
    FeasibilityAnnotation,
    TaskBoard,
    TaskNotFoundError,
    TaskStatus,
    annotate_feasibility,
    place_task,
    remove_task,
    set_task_status,
)


class TestDefaults:
    def test_acceptance_string_is_one_criterion_not_char_split(self) -> None:
        from molexp.harness.plan.task_board import coerce_acceptance

        # Bare str must not become tuple("…") character shredding.
        assert coerce_acceptance("脚本可对 N=10..50 生成链") == ("脚本可对 N=10..50 生成链",)
        task = BoardTask(id="t1", name="build", acceptance="molexp 创建成功")  # type: ignore[arg-type]
        assert task.acceptance == ("molexp 创建成功",)
        # Legacy shredded boards re-join on validate.
        shredded = BoardTask(
            id="t2",
            name="build",
            acceptance=tuple("molexp"),  # type: ignore[arg-type]
        )
        assert shredded.acceptance == ("molexp",)


class TestPlaceTask:
    def test_place_task_appends_and_bumps_version(self) -> None:
        board = TaskBoard()
        result = place_task(board, BoardTask(id="t1", name="build"))
        assert result.version == 1
        assert [t.id for t in result.tasks] == ["t1"]

    def test_place_task_upsert_replaces_same_id_without_duplicating(self) -> None:
        board = TaskBoard(tasks=(BoardTask(id="t1", name="old"),))
        result = place_task(board, BoardTask(id="t1", name="new"))
        assert len(result.tasks) == 1
        assert result.task("t1") is not None
        assert result.task("t1").name == "new"

    def test_place_task_does_not_mutate_input_board(self) -> None:
        board = TaskBoard()
        place_task(board, BoardTask(id="t1", name="build"))
        assert board.version == 0
        assert board.tasks == ()


class TestSetTaskStatus:
    def test_set_status_returns_new_board_with_changed_status(self) -> None:
        board = place_task(TaskBoard(), BoardTask(id="t1", name="build"))
        result = set_task_status(board, "t1", TaskStatus.BUILDING)
        assert result.version == board.version + 1
        assert result.task("t1").status is TaskStatus.BUILDING

    def test_set_status_does_not_mutate_input_board(self) -> None:
        board = place_task(TaskBoard(), BoardTask(id="t1", name="build"))
        set_task_status(board, "t1", TaskStatus.COMPLETE)
        assert board.task("t1").status is TaskStatus.PENDING

    def test_set_status_unknown_id_raises(self) -> None:
        with pytest.raises(TaskNotFoundError):
            set_task_status(TaskBoard(), "nope", TaskStatus.BUILDING)


class TestAnnotateFeasibility:
    def test_annotate_attaches_annotation_and_bumps_version(self) -> None:
        board = place_task(TaskBoard(), BoardTask(id="t1", name="build"))
        ann = FeasibilityAnnotation(
            reachable=True, difficulty=Difficulty.MODERATE, rationale="reachable"
        )
        result = annotate_feasibility(board, "t1", ann)
        assert result.version == board.version + 1
        assert result.task("t1").feasibility == ann

    def test_annotate_does_not_mutate_input_board(self) -> None:
        board = place_task(TaskBoard(), BoardTask(id="t1", name="build"))
        annotate_feasibility(board, "t1", FeasibilityAnnotation(reachable=True))
        assert board.task("t1").feasibility is None

    def test_annotate_unknown_id_raises(self) -> None:
        with pytest.raises(TaskNotFoundError):
            annotate_feasibility(TaskBoard(), "nope", FeasibilityAnnotation(reachable=True))


class TestRemoveTask:
    def test_remove_drops_task_and_bumps_version(self) -> None:
        board = place_task(TaskBoard(), BoardTask(id="t1", name="build"))
        result = remove_task(board, "t1")
        assert result.version == board.version + 1
        assert result.task("t1") is None
        assert result.tasks == ()

    def test_remove_does_not_mutate_input_board(self) -> None:
        board = place_task(TaskBoard(), BoardTask(id="t1", name="build"))
        remove_task(board, "t1")
        assert board.task("t1") is not None

    def test_remove_unknown_id_raises(self) -> None:
        with pytest.raises(TaskNotFoundError):
            remove_task(TaskBoard(), "nope")
