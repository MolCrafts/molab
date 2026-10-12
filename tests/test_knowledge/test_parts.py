"""GeneratedParts.list reads image artifacts; GeneratedParts.view writes a Report."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from molab.knowledge import GeneratedParts, Report

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_NARRATIVE = "The run emitted a hair layer."


def _succeed_with_parts(run: Any) -> None:
    with run.start() as ctx:
        work = ctx.get_dir("work")
        hair = work / "hair.png"
        eyes = work / "eyes.png"
        checkpoint = work / "checkpoint.png"
        hair.write_bytes(_PNG)
        eyes.write_bytes(_PNG)
        checkpoint.write_bytes(_PNG)
        ctx.emit_artifact(hair, name="hair.png", media_type="image/png", tags={"part": "hair"})
        ctx.emit_artifact(eyes, name="eyes.png", media_type="image/png", tags={"part": "eyes"})
        ctx.emit_artifact({"ok": True}, name="notes.json", media_type="application/json")
        ctx.emit_artifact(
            {"kind": "labeled"},
            name="label.json",
            media_type="application/json",
            tags={"part": "label"},
        )
        ctx.emit_artifact(
            checkpoint,
            name="checkpoint.png",
            media_type="image/png",
            semantic_type="checkpoint",
            tags={"part": "skip"},
        )


def test_lists_images_and_tagged_parts_and_skips_the_rest(run: Any) -> None:
    _succeed_with_parts(run)

    parts = GeneratedParts.list(run)

    assert [part.name for part in parts] == ["eyes.png", "hair.png", "label.json"]
    assert [part.part for part in parts] == ["eyes", "hair", "label"]
    hair = next(part for part in parts if part.part == "hair")
    assert hair.ref.startswith("molab:experiment/")
    assert hair.ref.endswith(f"/artifact/{hair.artifact_id}")
    assert Path(hair.path).is_file()
    assert hair.media_type == "image/png"


def test_view_parts_writes_a_report_with_a_ref_and_a_relative_image(run: Any) -> None:
    _succeed_with_parts(run)

    report = GeneratedParts.view(run, narrative=_NARRATIVE, created_by="tester")

    assert isinstance(report, Report)
    body = report.read()
    hair = next(part for part in GeneratedParts.list(run) if part.part == "hair")
    assert _NARRATIVE in body
    assert f"[@records hair]({hair.ref})" in body
    assert "![hair](" in body
    assert "![label](" not in body
    image_target = next(line for line in body.splitlines() if line.startswith("![hair]("))
    relative = image_target.removeprefix("![hair](").removesuffix(")")
    assert (Path(report.path).parent / relative).resolve() == Path(hair.path)
    roles = {(edge.role, edge.target) for edge in report.links()}
    assert ("records", hair.ref) in roles


def test_refuses_a_live_run_and_a_blank_narrative(run: Any) -> None:
    import pytest

    with pytest.raises(ValueError, match="terminal"):
        GeneratedParts.view(run, narrative=_NARRATIVE, created_by="tester")

    with run.start():
        pass
    with pytest.raises(ValueError, match="narrative"):
        GeneratedParts.view(run, narrative="  ", created_by="tester")
