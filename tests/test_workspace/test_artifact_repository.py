"""Unit tests for ``molab.workspace.artifact_repository`` (``AssetRepository``).

arch-own-02a-record: ``promote`` stamps ``asset.json`` and
``versions/vNNN.json`` with the current ``MOLAB_SCHEMA_VERSION`` like every
other workspace writer, instead of a hard-coded literal.
"""

from __future__ import annotations

import json
from pathlib import Path

from molab.workspace import Project, Run
from molab.workspace.history import AgentRef
from molab.workspace.schema_version import MOLAB_SCHEMA_VERSION


def _raw(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class TestAssetRepository:
    def test_promote_stamps_current_schema_version(self, project: Project, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact({"x": 1}, name="a.json")

        project.assets.promote(artifact, created_by=AgentRef(id="t", type="system"))

        asset_files = sorted((Path(project.project_dir) / "assets").glob("*/asset.json"))
        assert len(asset_files) == 1
        asset_root = asset_files[0].parent
        assert _raw(asset_root / "asset.json")["schema_version"] == MOLAB_SCHEMA_VERSION
        version_file = asset_root / "versions" / "v001.json"
        assert _raw(version_file)["schema_version"] == MOLAB_SCHEMA_VERSION
