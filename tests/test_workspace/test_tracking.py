"""``molab.print`` and the current execution (D92).

``molab.workspace.tracking`` holds the current execution in a contextvar.
``print`` is the builtin, plus a copy into the current execution's
``stdout.log`` / ``stderr.log``. These tests pin builtin parity, routing,
nesting, failure isolation, thread isolation, ``ctx.log`` interleaving and
the seal digest of the final bytes.
"""

from __future__ import annotations

import builtins
import contextvars
import hashlib
import io
import sys
import threading
from pathlib import Path

import pytest

import molab
from molab.workspace import tracking
from molab.workspace.domain import ExecutionStatus
from molab.workspace.tracking import current, print

_PRINT_CASES: list[tuple[tuple[object, ...], dict[str, object]]] = [
    (("a", 1, 2.5), {}),
    (("a", "b"), {"sep": "-"}),
    (("a", "b"), {"sep": None}),
    (("a", "b"), {"end": "|"}),
    (("a", "b"), {"end": None}),
    (("x",), {"sep": "", "end": ""}),
    ((), {}),
    (("flushed",), {"flush": True}),
]


def _stdout_log(ctx) -> Path:
    return ctx.execution_dir / "stdout.log"


def _stderr_log(ctx) -> Path:
    return ctx.execution_dir / "stderr.log"


class TestPublicSurface:
    def test_top_level_exports(self) -> None:
        assert molab.print is tracking.print
        assert molab.current is tracking.current
        assert {"print", "current"} <= set(molab.__all__)

    def test_execution_context_is_a_tracker(self, run) -> None:
        with run.start() as ctx:
            assert isinstance(ctx, tracking.Tracker)
            assert current() is ctx
        assert current() is None


class TestBuiltinParity:
    @pytest.mark.parametrize(("values", "kwargs"), _PRINT_CASES)
    def test_terminal_output_identical_inside_and_outside(
        self, run, capsys, values, kwargs
    ) -> None:
        builtins.print(*values, **kwargs)
        expected = capsys.readouterr()
        print(*values, **kwargs)
        outside = capsys.readouterr()
        with run.start() as ctx:
            print(*values, **kwargs)
        inside = capsys.readouterr()
        assert outside == expected
        assert inside == expected
        assert _stdout_log(ctx).read_text(encoding="utf-8") == expected.out

    def test_outside_an_execution_writes_nothing(self, run, capsys) -> None:
        print("loose")
        assert capsys.readouterr().out == "loose\n"
        with run.start() as ctx:
            pass
        assert not _stdout_log(ctx).exists()
        print("after")
        assert not _stdout_log(ctx).exists()


class TestRouting:
    def test_stdout_and_stderr_go_to_their_files(self, run, capsys) -> None:
        with run.start() as ctx:
            print("to out")
            print("to out explicitly", file=sys.stdout)
            print("to err", file=sys.stderr)
        captured = capsys.readouterr()
        assert captured.out == "to out\nto out explicitly\n"
        assert captured.err == "to err\n"
        assert _stdout_log(ctx).read_text(encoding="utf-8") == "to out\nto out explicitly\n"
        assert _stderr_log(ctx).read_text(encoding="utf-8") == "to err\n"

    def test_original_streams_are_routed(self, run, monkeypatch) -> None:
        out, err = io.StringIO(), io.StringIO()
        monkeypatch.setattr(sys, "__stdout__", out)
        monkeypatch.setattr(sys, "__stderr__", err)
        with run.start() as ctx:
            print("o", file=sys.__stdout__)
            print("e", file=sys.__stderr__)
        assert (out.getvalue(), err.getvalue()) == ("o\n", "e\n")
        assert _stdout_log(ctx).read_text(encoding="utf-8") == "o\n"
        assert _stderr_log(ctx).read_text(encoding="utf-8") == "e\n"

    def test_other_file_is_not_copied(self, run) -> None:
        sink = io.StringIO()
        with run.start() as ctx:
            print("private", file=sink)
        assert sink.getvalue() == "private\n"
        assert not _stdout_log(ctx).exists()
        assert not _stderr_log(ctx).exists()


class TestNesting:
    def test_inner_context_restores_outer(self, experiment) -> None:
        outer_run = experiment.add_run(params={"which": "outer"})
        inner_run = experiment.add_run(params={"which": "inner"})
        with outer_run.start() as outer:
            print("outer 1")
            with inner_run.start() as inner:
                assert current() is inner
                print("inner")
            assert current() is outer
            print("outer 2")
        assert current() is None
        assert _stdout_log(outer).read_text(encoding="utf-8") == "outer 1\nouter 2\n"
        assert _stdout_log(inner).read_text(encoding="utf-8") == "inner\n"

    def test_failed_enter_leaves_no_binding(self, run) -> None:
        with run.start():
            pass
        ctx = run.start(execution_id="e01")
        with pytest.raises(ValueError):
            ctx.__enter__()
        assert current() is None


class TestFailureIsolation:
    def test_failing_copy_does_not_raise(self, run, capsys, monkeypatch) -> None:
        warnings: list[str] = []

        class _Logger:
            def warning(self, msg: str, *_args: object, **_kwargs: object) -> None:
                warnings.append(msg)

        monkeypatch.setattr(tracking, "_warned", False)
        monkeypatch.setattr(tracking, "_logger", _Logger())
        with run.start() as ctx:

            def boom(*_args: object, **_kwargs: object) -> None:
                raise OSError("disk full")

            monkeypatch.setattr(ctx, "write_stdio", boom)
            print("still shown")
            print("again")
        assert capsys.readouterr().out == "still shown\nagain\n"
        assert len(warnings) == 1
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED


class TestConcurrency:
    def test_two_threads_two_executions(self, experiment) -> None:
        runs = [experiment.add_run(params={"t": i}) for i in range(2)]
        dirs: dict[int, Path] = {}
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def body(i: int) -> None:
            try:
                with runs[i].start() as ctx:
                    dirs[i] = ctx.execution_dir
                    barrier.wait()
                    for n in range(200):
                        print(f"thread {i} line {n}")
                    barrier.wait()
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=body, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        for i in range(2):
            lines = (dirs[i] / "stdout.log").read_text(encoding="utf-8").splitlines()
            assert lines == [f"thread {i} line {n}" for n in range(200)]

    def test_ctx_log_and_print_interleave_by_whole_lines(self, run) -> None:
        with run.start() as ctx:
            log = ctx.log("stdout")

            def printer() -> None:
                for n in range(300):
                    print(f"print {n} " + "x" * 50)

            def appender() -> None:
                for n in range(300):
                    log.append(f"append {n} " + "y" * 50)

            # A thread starts with an empty context; hand it this one, the way a
            # user does for a thread of their own (asyncio.to_thread does it).
            context = contextvars.copy_context()
            threads = [
                threading.Thread(target=context.run, args=(printer,)),
                threading.Thread(target=appender),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert len(log.tail(1000)) == 600
        lines = _stdout_log(ctx).read_text(encoding="utf-8").splitlines()
        assert sorted(lines) == sorted(
            [f"print {n} " + "x" * 50 for n in range(300)]
            + [f"append {n} " + "y" * 50 for n in range(300)]
        )
        assert [line for line in lines if line.startswith("print")] == [
            f"print {n} " + "x" * 50 for n in range(300)
        ]


class TestCtxLog:
    def test_log_stdout_shares_the_print_file(self, run) -> None:
        with run.start() as ctx:
            print("printed")
            ctx.log("stdout").append("appended")
            print("printed again")
            assert ctx.log("stdout").tail() == ["printed", "appended", "printed again"]

    def test_log_stdout_after_exit_still_appends(self, run) -> None:
        with run.start() as ctx:
            print("inside")
        ctx.log("stdout").append("late")
        assert _stdout_log(ctx).read_text(encoding="utf-8") == "inside\nlate\n"

    def test_run_log_keeps_its_own_file(self, run) -> None:
        with run.start() as ctx:
            ctx.log("run").append("progress")
            print("printed")
        assert "progress" in (ctx.execution_dir / "run.log").read_text(encoding="utf-8")
        assert _stdout_log(ctx).read_text(encoding="utf-8") == "printed\n"


class TestSeal:
    def test_evidence_digest_covers_final_bytes(self, run) -> None:
        with run.start() as ctx:
            for n in range(50):
                print(f"line {n}")  # buffered, not flushed
            print("err line", file=sys.stderr)
        sealed = run.executions[-1]
        by_kind = {item.kind: item for item in sealed.evidence}
        for kind, path in (("stdout", _stdout_log(ctx)), ("stderr", _stderr_log(ctx))):
            data = path.read_bytes()
            assert by_kind[kind].digest == f"sha256:{hashlib.sha256(data).hexdigest()}"
            assert by_kind[kind].size == len(data)
        assert _stdout_log(ctx).read_text(encoding="utf-8").count("\n") == 50
