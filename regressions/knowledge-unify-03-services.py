"""Goldens for knowledge-unify-03-services: analyze_run_failure writes Report."""

from __future__ import annotations

import inspect
from pathlib import Path

from molab.knowledge import Report, SourceRef
from molab.services import run_failure
from molab.services.run_failure import analyze_run_failure
from molab.workspace import Workspace


def main() -> None:
    src = inspect.getsource(run_failure)
    assert "from molab.knowledge import Report" in src
    assert "FailureAnalysis" not in src
    assert "Report," in src or "of=Report" in src

    root = Path().resolve()
    # Runtime path is exercised by tests/test_services/test_run_failure.py.
    # This regression pins the import + harvest class golden.
    assert analyze_run_failure.__annotations__["return"]
    _ = (Report, SourceRef, Workspace, root)


if __name__ == "__main__":
    main()
