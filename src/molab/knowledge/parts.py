"""List a run's generated image parts.

The bytes are the assets that attempt registered. :class:`GeneratedParts`
reads those assets. It does not write a second document about them. A harvest
cites the same assets when the narrative uses them.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from molab.workspace.domain import Asset
    from molab.workspace.run import Run

__all__ = ["GeneratedPart", "GeneratedParts"]


class GeneratedPart(NamedTuple):
    """One image (or explicitly tagged part) a run registered.

    Attributes:
        name: Asset title.
        part: ``tags["part"]`` when that tag is a non-empty string,
            otherwise the title.
        asset_id: Asset id.
        execution_id: Attempt that registered it.
        ref: ``molab:asset/<id>``.
        path: Path of the asset bytes.
        media_type: Recorded media type, if any.
    """

    name: str
    part: str
    asset_id: str
    execution_id: str
    ref: str
    path: str
    media_type: str | None


class GeneratedParts:
    """The image parts one run emitted.

    ``GeneratedParts(run).list()`` reads one attempt.
    """

    def __init__(self, run: Run) -> None:
        """Bind the run whose image parts this object lists."""
        self._run = run

    def list(
        self,
        *,
        execution_id: str | None = None,
    ) -> builtins.list[GeneratedPart]:
        """Image assets of one attempt, ordered by title.

        An asset is included when its media type starts with ``image/``, or
        when its tags carry a ``part`` key. The attempt is
        :meth:`~molab.workspace.run.Run.produced_assets`'s: the latest when
        *execution_id* is omitted, and none on a run with no attempt.

        Raises:
            ValueError: *execution_id* names no attempt of the run.
        """
        from molab.workspace.domain import ExecutionOrigin

        run = self._run
        found: list[GeneratedPart] = []
        for asset in run.produced_assets(execution_id):
            origin = asset.origin
            if not _is_part(asset) or not isinstance(origin, ExecutionOrigin):
                continue
            found.append(
                GeneratedPart(
                    name=asset.title,
                    part=_part_label(asset),
                    asset_id=asset.id,
                    execution_id=origin.execution_id,
                    ref=asset.ref,
                    path=run.asset_path(asset.id),
                    media_type=asset.media_type,
                )
            )
        found.sort(key=lambda item: item.name)
        return found


def _is_part(asset: Asset) -> bool:
    media = asset.media_type or ""
    if media.startswith("image/"):
        return True
    return "part" in asset.tags


def _part_label(asset: Asset) -> str:
    part = asset.tags.get("part")
    if isinstance(part, str) and part.strip():
        return part.strip()
    return asset.title
