# Open questions

Debts the arch-own chain recorded and did not close. Decided items are not listed here.

## Scheduler RESUME on a remote target recomputes

A scheduler RESUME against a remote target recomputes the attempt. The predecessor journal is not staged onto the worker, so completed nodes are not seeded. No owner.

## `molab migrate layout` writes migrated entity JSON directly

D74. `molab migrate layout` still writes the migrated `run.json`, `experiment.json`, `project.json`, and `workspace.json` with `_stamp` and `_write_json`, instead of folding them through the owner the way `fold_legacy_attempt` folds a legacy attempt. No owner in this chain. Named in CLAUDE.md invariant 3.

## Crepe `molab:` links are unverified

After knowledge documents may contain `molab:` links, clicking one in the Milkdown Crepe editor (`NoteEditor.tsx`) and proving a Crepe save round-trips `[x](molab:…)` byte for byte has not been checked.

## `molab:asset/<id>` stays unresolved in markdown

Asset responses carry no server ref, so a `molab:asset/<id>` link renders as unresolved text. The asset response shape is owned elsewhere.

## Missing upstream evidence file

The comparison that rejected Temporal, Ray, AiiDA, and PSI/J as workflow-engine replacements is not in the tree. The verdict (they lose on one source of truth and on one-wheel distribution) stays in CLAUDE.md. The evidence file itself is missing.

## Run lock is keyed by a bare run id

The run lock uses the bare run id. Accepted legacy debt from the execution-mode work. `qualify_run_id` remains the permanent qualifier when a bare id must be turned into a `molab:` ref.
