# Open questions

Debts the arch-own chain recorded and did not close. Decided items are not listed here.

## Scheduler RESUME on a remote target recomputes

A scheduler RESUME against a remote target recomputes the attempt. The predecessor journal is not staged onto the worker, so completed nodes are not seeded. No owner.

## `molab migrate layout` builds migrated records unvalidated

D74. Since D88, `molab migrate layout` writes each migrated run, experiment, project and workspace record as the frontmatter of the level's `index.md` through the owner's `entity_record.write_record` (and rebuilds the derived `index:` blocks), but it still builds each canonical zone itself with `_stamp`, without validating it through the level's `*Metadata` model the way `fold_legacy_attempt` validates a legacy attempt. A v5 tree written by the current schema should use `molab migrate index`, which does validate. No owner in this chain. Named in CLAUDE.md invariant 3.

## Crepe `molab:` links are unverified

After knowledge documents may contain `molab:` links, clicking one in the Milkdown Crepe editor (`NoteEditor.tsx`) and proving a Crepe save round-trips `[x](molab:…)` byte for byte has not been checked.

## `molab:asset/<id>` stays unresolved in markdown

Asset responses carry no server ref, so a `molab:asset/<id>` link renders as unresolved text. The asset response shape is owned elsewhere.

## Missing upstream evidence file

The comparison that rejected Temporal, Ray, AiiDA, and PSI/J as workflow-engine replacements is not in the tree. The verdict (they lose on one source of truth and on one-wheel distribution) stays in CLAUDE.md. The evidence file itself is missing.

## Run lock is keyed by a bare run id

The run lock uses the bare run id. Accepted legacy debt from the execution-mode work. `qualify_run_id` remains the permanent qualifier when a bare id must be turned into a `molab:` ref.

## `set_active_task` races under parallel tasks

D92 (track-01). `ExecutionContext.set_active_task` is one slot per execution. The engine sets it before each task body (`workflow/_engine/node.py` `run_task_body`, and the cache-hit path in `node_cache.py`), and `ExecutionContext._emit` reads it to stamp an artifact's `metadata.task_id`. Same-level tasks run in parallel, so a body (or its `_promote_outputs`) can read the name a sibling set a moment later, and an artifact can be tagged with the wrong producer task. Remedy (track-02): read `molab.workspace.tracking.current_task()`, which the engine sets per body with `tracking.task_scope(name)` in that task's own context copy, and drop the slot. Track-01 keeps the slot's semantics unchanged.

## Evidence after an early seal

D92 (track-01). `ExecutionContext.__exit__` closes `stdout.log` / `stderr.log` before `ExecutionRepository.seal` hashes them, so a normal exit seals the final bytes. Not covered: an attempt sealed from outside while its body still runs (`run.cancel`, `lifecycle_ops.cancel_run`, the zombie reaper). Its evidence is hashed at that seal, the body keeps printing into `stdout.log`, and `__exit__`'s own seal is a no-op on a sealed record, so the recorded digest no longer matches the file. The same already held for `run.log` (`_emit_results` appends "results not recorded" after an early seal) and for a `ctx.log("stdout").append` after exit, which still appends (call style kept). Options: stop copying into an attempt once it is observed sealed, or record post-seal growth as its own fact. No owner.
