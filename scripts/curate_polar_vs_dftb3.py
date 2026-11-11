"""Curate the peo-polar-length/n-series Polar-vs-DFTB+ parity asset.

The parity study (``assets/polar_vs_dftb3``) was built by hand in the legacy
``lab`` workspace over 2026-09-04..05 and copied verbatim into ``lab-v3`` by
``WorkspaceSynced`` (47af5c53). That copy carried everything the exploration
left behind: a superseded n=8 shortcut, 30 LAMMPS restart files of a finished
anneal, the logs of every failed or wrong-result Slurm attempt, and drivers
whose absolute paths still point at ``lab/``.

This script makes the asset read as a result instead of a scratch dir:

* deletes the superseded ``n8_gudla_gamma`` point, the ``n8.restart.*`` files,
  the failed resume logs, the failed / pre-fix 420 K job logs, ``__pycache__``
  and the two job-id scratch lists (their ids live in ``README.md`` now);
* deletes the dead Gudla watcher at the experiment root (it polled legacy
  ``run-<hash>`` dirs that no longer exist in lab-v3);
* re-points every driver (``*.py``, ``*.sh``) from ``work/lab/projects`` to
  ``work/lab-v3/projects``, fixes the ``sbatch_polar3.sh`` log path that
  lacked ``assets/``, and maps the two schema-2 run dirs in
  ``npt420_10frames/setup.py`` onto their lab-v3 names;
* drops the now-pointless per-file ``.gitignore`` lines for deleted files.

Slurm logs are never rewritten: they are records of where a job ran.

It is replayable and idempotent: run it on a freshly migrated archive (and on
the legacy ``lab`` source, whose n-series tree has the same relative layout)
and you get the same tree.

Usage:  python scripts/curate_polar_vs_dftb3.py <workspace-root> [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

EXP = Path("projects/peo-polar-length/experiments/n-series")
ASSET = EXP / "assets/polar_vs_dftb3"
NPT = ASSET / "npt420_10frames"

# Directories to remove outright.
DIRS = [
    ASSET / "n8_gudla_gamma",  # 44-min NPT shortcut; superseded by n8_gudla_full
    NPT / "__pycache__",
    EXP / "__pycache__",
]

# Files to remove (relative to the workspace root). Slurm ids are listed by
# what sacct says about them, see assets/polar_vs_dftb3/README.md.
FILES = [
    NPT / "jobs.txt",
    NPT / "polar_jobs.txt",
    EXP / "watch_gudla_then_bench.py",
    EXP / ".watch_gudla_bench.json",
    EXP / "watch_gudla_then_bench.log",
]
_FAILED_LOGS = {
    ASSET / "n8_gudla_full": ["slurm-gudla-2048545", "slurm-gudla-2051944"],
    NPT / "n2": [
        "slurm-npt-2057960",
        "slurm-npt-2058100",
        "slurm-npt-2058193",
        "slurm-npt-2059980",
        "slurm-npt-2060230",
        "slurm-polar-2058194",
        "slurm-polar-2060254",
        "slurm-polar-2061972",
    ],
    NPT / "n4": [
        "slurm-npt-2057962",
        "slurm-npt-2058195",
        "slurm-npt-2059982",
        "slurm-npt-2060232",
        "slurm-polar-2060256",
        "slurm-polar-2061973",
    ],
    NPT / "n8": [
        "slurm-npt-2057964",
        "slurm-npt-2058197",
        "slurm-npt-2059984",
        "slurm-npt-2060234",
        "slurm-polar-2060258",
        "slurm-polar-2061974",
    ],
}
for _dir, _stems in _FAILED_LOGS.items():
    for _stem in _stems:
        FILES += [_dir / f"{_stem}.out", _dir / f"{_stem}.err"]

GLOBS = [(ASSET / "n8_gudla_full", "n8.restart.*")]

# Text rewrites applied to every *.py / *.sh under the experiment (runs/ excluded).
LAB = "/nobackup/proj/disk/teoroo/personal/jicli594/work/lab/projects/"
LAB_V3 = "/nobackup/proj/disk/teoroo/personal/jicli594/work/lab-v3/projects/"
HOME_LAB = "/home/jicli594/work/lab/projects/"
HOME_LAB_V3 = "/home/jicli594/work/lab-v3/projects/"
REWRITES: list[tuple[str, str]] = [
    (LAB, LAB_V3),
    (HOME_LAB, HOME_LAB_V3),
    # sbatch_polar3.sh wrote its logs one level too high (no assets/).
    ("n-series/polar_vs_dftb3/slurm-", "n-series/assets/polar_vs_dftb3/slurm-"),
    ("OUT=$HERE/polar_vs_dftb3", "OUT=$HERE/assets/polar_vs_dftb3"),
    # npt420_10frames/setup.py: schema-2 run dirs -> lab-v3 names
    # (ExecutionDirsRenamed 59bd82aa: work/ -> out/).
    (
        "runs/run-2bc7593146fca591/executions/exec-2bc7593146fca591-5/work/gudla_anneal/gudla",
        "runs/n=2/executions/e05/out/gudla_anneal/gudla",
    ),
    (
        "runs/run-d0345dcbf56bb088/executions/exec-d0345dcbf56bb088-4/work/gudla_anneal/gudla",
        "runs/n=4/executions/e04/out/gudla_anneal/gudla",
    ),
]

GITIGNORE_DROP = (
    "/projects/peo-polar-length/experiments/n-series/assets/polar_vs_dftb3/n8_gudla_full/n8.restart.",
    "/projects/peo-polar-length/experiments/n-series/assets/polar_vs_dftb3/n8_gudla_gamma/",
)


def _scripts(root: Path) -> Iterator[Path]:
    exp = root / EXP
    for p in sorted(exp.rglob("*")):
        if p.suffix not in {".py", ".sh"} or not p.is_file():
            continue
        if "runs" in p.relative_to(exp).parts:
            continue
        yield p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args(argv)
    root: Path = ns.root.resolve()
    dry = ns.dry_run
    if not (root / EXP).is_dir():
        print(f"no n-series experiment under {root}", file=sys.stderr)
        return 2

    def say(m: str) -> None:
        print(("DRY " if dry else "") + m)

    n_rm = 0
    for d in DIRS:
        p = root / d
        if p.is_dir():
            say(f"rm -r {d}")
            n_rm += 1
            if not dry:
                shutil.rmtree(p)
    targets = [root / f for f in FILES]
    for d, pat in GLOBS:
        targets += sorted((root / d).glob(pat))
    for p in targets:
        if p.is_file():
            say(f"rm {p.relative_to(root)}")
            n_rm += 1
            if not dry:
                p.unlink()

    n_rw = 0
    for p in _scripts(root):
        text = p.read_text(encoding="utf-8")
        new = text
        for old, rep in REWRITES:
            new = new.replace(old, rep)
        if new != text:
            say(f"rewrite {p.relative_to(root)}")
            n_rw += 1
            if not dry:
                p.write_text(new, encoding="utf-8")

    gi = root / ".gitignore"
    if gi.is_file():
        lines = gi.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [ln for ln in lines if not ln.startswith(GITIGNORE_DROP)]
        if len(kept) != len(lines):
            say(f".gitignore: drop {len(lines) - len(kept)} stale lines")
            if not dry:
                gi.write_text("".join(kept), encoding="utf-8")

    say(f"done: {n_rm} paths removed, {n_rw} scripts re-pointed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
