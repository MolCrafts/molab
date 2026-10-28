"""CommandTask — run one external command, check its return code, fail on nonzero.

A reusable batch :class:`~molab.workflow.task.Task` that collapses the
recurring "run a command, check ``returncode``, raise on non-zero" wrapper
block into one primitive. A non-zero exit surfaces as a
:class:`~molab.workflow.types.CommandError` (a ``WorkflowError``) carrying the
command's ``returncode`` / ``stdout`` / ``stderr``.

Two construction paths, exactly one supplied:

* **argv** — ``CommandTask(["antechamber", "-i", ...])`` runs the list as a
  subprocess via :func:`subprocess.run` (capturing stdout/stderr; honoring an
  optional ``cwd`` / ``env`` / ``timeout``).
* **runner** — ``CommandTask(runner=fn)`` calls a zero-arg callable returning
  any object exposing ``.returncode`` / ``.stdout`` / ``.stderr``. This lets
  callers (e.g. molpy wrapper tasks) reuse ``CommandTask`` without molab
  depending on molpy — the wrapper is invoked in the caller's closure and
  ``CommandTask`` only reads the three attributes off the result.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mollog import get_logger

from molab.workflow.task import Task
from molab.workflow.types import CommandError
from molab.workspace import tracking

if TYPE_CHECKING:
    from molab.workflow.context import TaskContext

_logger = get_logger(__name__)


def _as_str(value: Any) -> str:  # noqa: ANN401 — duck-typed stream attr (str | bytes | None)
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value if isinstance(value, str) else str(value)


def _archive_stdio(stdout: str, stderr: str) -> None:
    """Append a finished command's captured streams to the current execution.

    The child's output lands in ``stdout.log`` / ``stderr.log`` beside the
    lines ``molab.print`` wrote (D92), each stream as one write ending in a
    newline. Outside an execution nothing is written. A failure is logged and
    never fails the task.
    """
    tracker = tracking.current()
    if tracker is None:
        return
    for stream, text in (("stdout", stdout), ("stderr", stderr)):
        if not text:
            continue
        try:
            tracker.write_stdio(stream, text if text.endswith("\n") else text + "\n")
        except Exception:
            _logger.warning(
                f"could not record the command's {stream} in the execution", exc_info=True
            )


@dataclass(frozen=True)
class CommandResult:
    """Normalized outcome of a command: its return code and captured streams."""

    returncode: int
    stdout: str
    stderr: str


class CommandTask(Task):
    """Run one external command and fail the workflow on a non-zero return code.

    Inside an execution, the command's captured stdout / stderr are also
    appended to that execution's ``stdout.log`` / ``stderr.log`` (on success
    and on failure); the return value is unchanged.

    Args:
        argv: The command + arguments to run as a subprocess. Mutually exclusive
            with *runner*.
        runner: A zero-arg callable returning an object with ``.returncode`` /
            ``.stdout`` / ``.stderr``. Mutually exclusive with *argv*.
        cwd: Working directory for the argv subprocess (ignored for *runner*).
        env: Environment mapping for the argv subprocess (ignored for *runner*).
        timeout: Optional wall-clock timeout (seconds) for the argv subprocess.

    Raises:
        ValueError: If both or neither of *argv* / *runner* are supplied.
    """

    def __init__(
        self,
        argv: Sequence[str] | None = None,
        *,
        runner: Callable[[], Any] | None = None,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        if (argv is None) == (runner is None):
            raise ValueError("CommandTask requires exactly one of `argv` or `runner`")
        self._argv = list(argv) if argv is not None else None
        self._runner = runner
        self._cwd = cwd
        self._env = dict(env) if env is not None else None
        self._timeout = timeout

    async def execute(self, ctx: TaskContext) -> CommandResult:  # noqa: ARG002 — argv/runner ignore ctx
        """Run the command and return its :class:`CommandResult`.

        Returns:
            The normalized result on a zero return code.

        Raises:
            CommandError: If the command exits with a non-zero return code; the
                error carries ``returncode`` / ``stdout`` / ``stderr``.
        """
        if self._runner is not None:
            raw = self._runner()
            result = CommandResult(int(raw.returncode), _as_str(raw.stdout), _as_str(raw.stderr))
        else:
            completed = subprocess.run(
                self._argv if self._argv is not None else [],
                capture_output=True,
                text=True,
                cwd=self._cwd,
                env=self._env,
                timeout=self._timeout,
                check=False,
            )
            result = CommandResult(
                completed.returncode, _as_str(completed.stdout), _as_str(completed.stderr)
            )
        _archive_stdio(result.stdout, result.stderr)
        if result.returncode != 0:
            raise CommandError(result.returncode, result.stdout, result.stderr)
        return result
