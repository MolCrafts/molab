"""GeneratedParts(run).list reads registered image assets. It does not write."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from molab.knowledge import GeneratedParts

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _succeed_with_parts(run: Any) -> None:
    with run.start() as ctx:
        work = ctx.get_dir("work")
        hair = work / "hair.png"
        eyes = work / "eyes.png"
        hair.write_bytes(_PNG)
        eyes.write_bytes(_PNG[:-1] + bytes([_PNG[-1] ^ 0x01]))
        ctx.register(hair, title="hair.png", media_type="image/png", tags={"part": "hair"})
        ctx.register(eyes, title="eyes.png", media_type="image/png", tags={"part": "eyes"})
        ctx.register({"ok": True}, title="notes.json", media_type="application/json")
        ctx.register(
            {"kind": "labeled"},
            title="label.json",
            media_type="application/json",
            tags={"part": "label"},
        )
        # A checkpoint is a path under checkpoints/, not an asset, so it is not a part.
        ctx.checkpoint("skip", data={"kept": False})


def test_lists_images_and_tagged_parts_and_skips_the_rest(run: Any) -> None:
    _succeed_with_parts(run)

    parts = GeneratedParts(run).list()

    assert [part.name for part in parts] == ["eyes.png", "hair.png", "label.json"]
    assert [part.part for part in parts] == ["eyes", "hair", "label"]
    hair = next(part for part in parts if part.part == "hair")
    assert hair.ref == f"molab:asset/{hair.asset_id}"
    assert Path(hair.path).is_file()
    assert hair.media_type == "image/png"
    assert not hasattr(GeneratedParts, "view")
