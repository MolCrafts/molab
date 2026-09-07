"""Rename an existing workspace's attempt directories onto the three tiers.

Before, two directories with backwards names::

    executions/e01/out/     # promoted products — kept in git
    executions/e01/work/    # everything else the attempt wrote — gitignored

"out" was the curated one and "work" was where the trajectories actually
lived, so the name a person reads said the opposite of what the directory
held. After::

    executions/e01/artifacts/   # promoted, registered, citable  (was out/)
    executions/e01/out/         # bulk output the attempt wrote  (was work/)
    executions/e01/work/        # scratch — new, empty for old attempts

The old ``work/`` becomes ``out/`` rather than staying put: it holds
antechamber droppings and the trajectory side by side, the two cannot be
told apart after the fact, and ``work/`` is the tier declared safe to delete
whole. Nothing that might be a result is left somewhere a prune may remove.

Only two recorded paths are live and get rewritten — an artifact's ``path``
and ``source_path`` on ``execution.json``. Every other path in the tree is a
*historical* absolute path into the old ``lab`` workspace, recording where a
job actually ran; rewriting those would falsify the record.

Usage::

    python scripts/migrate_execution_dirs.py <workspace> [--apply]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from molexp.workspace.execution_dirs import ARTIFACTS, OUT, WORK
from molexp.workspace.history import default_gitignore

#: Old directory -> new directory, applied in this order. ``out`` must move
#: first or renaming ``work`` would collide with it.
RENAMES: tuple[tuple[str, str], ...] = ((OUT.name, ARTIFACTS.name), (WORK.name, OUT.name))


@dataclass
class Report:
    attempts: int = 0
    renamed: list[str] = field(default_factory=list)
    records_rewritten: int = 0
    paths_rewritten: int = 0
    gitignore_entries: int = 0
    skipped: list[str] = field(default_factory=list)


def _execution_dirs(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.glob("projects/*/experiments/*/runs/*/executions/*")
        if path.is_dir() and re.fullmatch(r"e\d+", path.name)
    )


def _rewrite_record(record: dict, attempt_rel: str) -> int:
    """Point one artifact record at the tier its bytes moved to."""
    changed = 0

    path = record.get("path")
    if isinstance(path, str) and f"{attempt_rel}/{OUT.name}/" in path:
        record["path"] = path.replace(
            f"{attempt_rel}/{OUT.name}/", f"{attempt_rel}/{ARTIFACTS.name}/", 1
        )
        changed += 1

    # ``source_path`` is attempt-relative, so it shifts by the same renames:
    # a product promoted out of the old scratch now came from ``out/``, and
    # one that was already durable now came from ``artifacts/``.
    source = record.get("source_path")
    if isinstance(source, str):
        for old, new in RENAMES:
            if source == old or source.startswith(f"{old}/"):
                record["source_path"] = new + source[len(old) :]
                changed += 1
                break

    return changed


def _migrate_attempt(attempt: Path, root: Path, report: Report, *, apply: bool) -> None:
    report.attempts += 1
    attempt_rel = attempt.relative_to(root).as_posix()

    # Planned state, not the live directory: the renames are sequential, so
    # probing disk would make a dry run see a collision that the second step
    # of an --apply never hits — and then report differently from what it does.
    present = {child.name for child in attempt.iterdir() if child.is_dir()}

    if ARTIFACTS.name in present:
        report.skipped.append(f"{attempt_rel}: already has {ARTIFACTS.name}/")
        return

    for old, new in RENAMES:
        if old not in present:
            continue
        if new in present:
            report.skipped.append(f"{attempt_rel}: {new}/ already exists")
            return
        present.discard(old)
        present.add(new)
        report.renamed.append(f"{attempt_rel}: {old}/ -> {new}/")
        if apply:
            (attempt / old).rename(attempt / new)

    state = attempt / "execution.json"
    if not state.is_file():
        return
    document = json.loads(state.read_text(encoding="utf-8"))
    changed = 0
    for record in document.get("artifacts") or []:
        if isinstance(record, dict):
            changed += _rewrite_record(record, attempt_rel)
    if changed:
        report.records_rewritten += 1
        report.paths_rewritten += changed
        if apply:
            state.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")


def _migrate_gitignore(root: Path, report: Report, *, apply: bool) -> None:
    """Regenerate the rules, keeping the explicit oversize list intact.

    Those entries name individual files that are too big for the history.
    Any of them under an attempt's old ``out/`` now lives in ``artifacts/``,
    so the path has to follow or the bytes silently come back.
    """
    ignore = root / ".gitignore"
    if not ignore.is_file():
        return
    existing = ignore.read_text(encoding="utf-8").splitlines()

    marker = "# Oversize"
    tail_at = next((i for i, line in enumerate(existing) if line.startswith(marker)), None)
    tail: list[str] = []
    if tail_at is not None:
        for line in existing[tail_at:]:
            moved = re.sub(r"(/executions/e\d+)/out/", rf"\1/{ARTIFACTS.name}/", line)
            if moved != line:
                report.gitignore_entries += 1
            tail.append(moved)

    rendered = default_gitignore()
    if tail:
        rendered = rendered.rstrip("\n") + "\n\n" + "\n".join(tail).rstrip("\n") + "\n"
    if apply:
        ignore.write_text(rendered, encoding="utf-8")


def migrate(root: Path, *, apply: bool) -> Report:
    report = Report()
    for attempt in _execution_dirs(root):
        _migrate_attempt(attempt, root, report, apply=apply)
    _migrate_gitignore(root, report, apply=apply)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--apply", action="store_true", help="write; default is a dry run")
    args = parser.parse_args()

    root = args.workspace.expanduser().resolve()
    if not (root / "workspace.json").is_file():
        print(f"not a molexp workspace: {root}", file=sys.stderr)
        return 2

    report = migrate(root, apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"[{mode}] {root}")
    print(f"  attempts scanned      {report.attempts}")
    print(f"  directories renamed   {len(report.renamed)}")
    print(f"  execution.json edited {report.records_rewritten}")
    print(f"  artifact paths fixed  {report.paths_rewritten}")
    print(f"  gitignore entries     {report.gitignore_entries}")
    for line in report.renamed[:8]:
        print(f"    {line}")
    if len(report.renamed) > 8:
        print(f"    … {len(report.renamed) - 8} more")
    for line in report.skipped:
        print(f"  SKIPPED {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
