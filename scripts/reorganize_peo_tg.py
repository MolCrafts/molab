"""Normalize the peo-tg project into two experiments with one honest axis set.

The project drifted into three experiments that were really three slices of
one parameter space, sliced inconsistently:

* ``size-convergence`` wrote only ``dp x n_chains x protocol=gudla2024``. The
  three force-field axes were hidden inside that ``protocol`` token
  (gudla2024 = GAFF + ethoxy + coul_14 0.8333), so two runs that differ in
  nothing looked different, and two that differ in a force field looked the
  same.
* ``c-paper-size`` re-ran the *same five cells* with those axes spelled out
  (its own docstring says so), producing a second copy of every cell.
* ``ff-regression`` left ``coul_14`` off three of its runs, where the driver's
  default of 0.8333 applied.

This script rewrites the archive so every run states all six axes:
``coul_14, dp, end_group, force_field, n_chains, seed``. ``protocol`` is
dropped — it was never a variable, only a name for three fixed values.
``c-paper-size`` disappears into ``size-convergence``: a cell re-run is more
attempts on the *same* Run, which is what the Execution model is for.

It is replayable: run it on a freshly migrated archive whenever the live jobs
in the source workspace finish, and you get the same tree.

Usage:  python scripts/reorganize_peo_tg.py <workspace-root> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from molexp.ids import compute_definition_hash
from molexp.workspace.naming import disambiguate, execution_slug, run_slug

#: What ``protocol=gudla2024`` actually stood for (Gudla & Zhang, JPCB 2024).
GUDLA2024 = {"end_group": "ethoxy", "force_field": "gaff", "coul_14": 0.8333}

#: The driver's default when a run left the 1-4 Coulomb scaling unstated.
DEFAULT_COUL_14 = 0.8333

#: The one seed every production cell was run at.
DEFAULT_SEED = 42

AXES = ("coul_14", "dp", "end_group", "force_field", "n_chains", "seed")


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize(params: dict[str, Any]) -> dict[str, Any]:
    """Return *params* with every axis stated and no stand-in tokens left."""
    out = dict(params)
    if out.pop("protocol", None) == "gudla2024":
        for key, value in GUDLA2024.items():
            out.setdefault(key, value)
    out.setdefault("coul_14", DEFAULT_COUL_14)
    out.setdefault("seed", DEFAULT_SEED)
    missing = [axis for axis in AXES if axis not in out]
    if missing:
        raise ValueError(f"cannot normalize {params}: no value for {missing}")
    return {axis: out[axis] for axis in AXES}


class Reorg:
    """Apply the normalization to one workspace, reporting what it did."""

    def __init__(self, root: Path, *, dry_run: bool = False) -> None:
        self.experiments = root / "projects" / "peo-tg" / "experiments"
        self.root = root
        self.dry_run = dry_run
        self.log: list[str] = []

    def say(self, line: str) -> None:
        self.log.append(line)
        print(line)

    # ── steps ────────────────────────────────────────────────────────────

    def drop_empty_runs(self, experiment: str) -> int:
        """Delete runs that only ever recorded a submitted job, never data."""
        runs = self.experiments / experiment / "runs"
        dropped = 0
        for run_dir in sorted(d for d in runs.iterdir() if d.is_dir()):
            # "Never ran" means no scientific bytes anywhere under the run —
            # no scratch, no products. A submitted-then-cancelled job leaves a
            # scheduler script and nothing else, and that is what goes.
            has_data = any(
                d.is_dir() and any(d.iterdir())
                for d in run_dir.glob("executions/*/*")
                if d.name in {"work", "out"}
            )
            if not has_data:
                self.say(f"  drop  {experiment}/{run_dir.name}  (never ran)")
                if not self.dry_run:
                    shutil.rmtree(run_dir)
                dropped += 1
        return dropped

    def restate_axes(self, experiment: str) -> None:
        """Spell out every axis on each run, and rename the run to match."""
        runs = self.experiments / experiment / "runs"
        taken: set[str] = set()
        for run_dir in sorted(d for d in runs.iterdir() if d.is_dir()):
            definition = read(run_dir / "run.json")
            params = normalize(definition.get("parameters") or {})
            definition["parameters"] = params
            definition["definition_hash"] = compute_definition_hash(
                {
                    "experiment_revision_id": definition.get("experiment_revision_id"),
                    "parameters": params,
                    "workflow_snapshot": definition.get("workflow_snapshot"),
                    "input_asset_ids": definition.get("input_asset_ids") or [],
                }
            )
            slug = disambiguate(run_slug(params, fallback=definition["definition_hash"]), taken)
            taken.add(slug)
            if not self.dry_run:
                write(run_dir / "run.json", definition)
            if slug != run_dir.name:
                self.say(f"  name  {experiment}/{run_dir.name}\n          -> {slug}")
                if not self.dry_run:
                    run_dir.rename(runs / slug)

    def absorb(self, source: str, target: str) -> None:
        """Fold *source*'s runs into *target*, cell by cell.

        A cell present in both is the same Run re-run, so its attempts join
        the target Run's attempts and are re-numbered in time order. A cell
        only in the source moves across whole.
        """
        src_runs = self.experiments / source / "runs"
        dst_runs = self.experiments / target / "runs"
        if not src_runs.is_dir():
            return
        for run_dir in sorted(d for d in src_runs.iterdir() if d.is_dir()):
            target_dir = dst_runs / run_dir.name
            if target_dir.is_dir():
                self.say(f"  merge {source}/{run_dir.name} -> {target} (same cell)")
                if not self.dry_run:
                    self._move_attempts(run_dir, target_dir)
                    shutil.rmtree(run_dir)
            else:
                self.say(f"  move  {source}/{run_dir.name} -> {target} (new cell)")
                if not self.dry_run:
                    run_dir.rename(target_dir)
        if not self.dry_run:
            shutil.rmtree(self.experiments / source)
        self.say(f"  gone  {source} (absorbed into {target})")

    def _move_attempts(self, src_run: Path, dst_run: Path) -> None:
        staged: list[tuple[str, Path]] = []
        for attempt in sorted((src_run / "executions").iterdir()):
            if not attempt.is_dir():
                continue
            state = read(attempt / "execution.json")
            parked = dst_run / "executions" / f"_incoming_{attempt.name}"
            attempt.rename(parked)
            staged.append((str(state.get("created_at", "")), parked))
        self._renumber(dst_run, extra=staged)

    def renumber(self, experiment: str) -> None:
        for run_dir in sorted((self.experiments / experiment / "runs").iterdir()):
            if run_dir.is_dir() and not self.dry_run:
                self._renumber(run_dir)

    def _renumber(self, run_dir: Path, *, extra: list[tuple[str, Path]] | None = None) -> None:
        """Re-number a Run's attempts e01..eNN in the order they were created."""
        executions = run_dir / "executions"
        if not executions.is_dir():
            return
        entries: list[tuple[str, Path]] = list(extra or [])
        for attempt in sorted(executions.iterdir()):
            if attempt.is_dir() and not attempt.name.startswith("_incoming_"):
                state = read(attempt / "execution.json")
                entries.append((str(state.get("created_at", "")), attempt))
        entries.sort(key=lambda item: (item[0], item[1].name))

        definition = read(run_dir / "run.json")
        for index, (_, attempt) in enumerate(entries, start=1):
            attempt.rename(executions / f"_staged_{index:03d}")
        for index in range(1, len(entries) + 1):
            staged = executions / f"_staged_{index:03d}"
            final = executions / execution_slug(index)
            staged.rename(final)
            self._restate_attempt(final, seq=index, run=definition)

    def _restate_attempt(self, attempt: Path, *, seq: int, run: dict) -> None:
        """Point an attempt's record at where it now lives."""
        state = read(attempt / "execution.json")
        slug = execution_slug(seq)
        state["id"] = slug
        state["seq"] = seq
        state["run_id"] = run["id"]
        rel = attempt.relative_to(self.root).as_posix()
        for artifact in state.get("artifacts") or []:
            artifact["execution_id"] = slug
            artifact["run_id"] = run["id"]
            tail = str(artifact.get("path", "")).split("/executions/", 1)
            if len(tail) == 2:
                artifact["path"] = f"{rel}/{tail[1].split('/', 1)[1]}"
        if state.get("based_on_execution_id"):
            state["based_on_execution_id"] = execution_slug(max(1, seq - 1))
        write(attempt / "execution.json", state)

    def restate_experiment(self, experiment: str) -> None:
        """Record the axes the experiment now scans."""
        path = self.experiments / experiment / "experiment.json"
        if not path.is_file():
            return
        metadata = read(path)
        space: dict[str, list[Any]] = {}
        for run_dir in sorted((self.experiments / experiment / "runs").iterdir()):
            if not run_dir.is_dir():
                continue
            for axis, value in (read(run_dir / "run.json").get("parameters") or {}).items():
                space.setdefault(axis, [])
                if value not in space[axis]:
                    space[axis].append(value)
        metadata["parameter_space"] = {k: sorted(v, key=str) for k, v in sorted(space.items())}
        if not self.dry_run:
            write(path, metadata)
        varying = [k for k, v in metadata["parameter_space"].items() if len(v) > 1]
        self.say(f"  axes  {experiment}: varies {varying or '(nothing)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="workspace root (e.g. ./lab-v3)")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    reorg = Reorg(args.root.resolve(), dry_run=args.dry_run)
    if not reorg.experiments.is_dir():
        print(f"no peo-tg project under {args.root}", file=sys.stderr)
        return 1

    print("1. drop runs that never ran")
    reorg.drop_empty_runs("size-convergence")
    print("2. state every axis on every run")
    for experiment in ("size-convergence", "c-paper-size", "ff-regression"):
        if (reorg.experiments / experiment).is_dir():
            reorg.restate_axes(experiment)
    print("3. fold c-paper-size into size-convergence")
    reorg.absorb("c-paper-size", "size-convergence")
    print("4. re-number attempts in time order")
    for experiment in ("size-convergence", "ff-regression"):
        reorg.renumber(experiment)
    print("5. record what each experiment scans")
    for experiment in ("size-convergence", "ff-regression", "molpack-grow"):
        reorg.restate_experiment(experiment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
