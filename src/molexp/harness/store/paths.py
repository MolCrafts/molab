"""On-disk homes for harness stores under a run directory.

Science products live at ``executions/<id>/artifacts/``. Pipeline (plan /
curate) bytes live under ``harness/`` so the two stores never share a
directory name.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["HARNESS_DIRNAME", "harness_artifact_root"]

HARNESS_DIRNAME = "harness"


def harness_artifact_root(run_dir: str | Path) -> Path:
    """``<run_dir>/harness/artifacts`` — FileArtifactStore root for this run."""
    return Path(run_dir) / HARNESS_DIRNAME / "artifacts"
