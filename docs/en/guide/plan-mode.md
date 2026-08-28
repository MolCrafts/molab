# Planning with the Agent Harness

`molexp plan` turns a natural-language experiment draft into:

1. a **task board** (ordered steps + acceptance criteria),
2. a **human review** (approvals inbox / TTY / `--yes`),
3. a **frozen plan** plus a readable **plan report**.

Phase 2 — **deterministic realization** (per-task codegen + a compile-only
dry run) — is a separate phase of the pipeline that this command does not
drive yet: `molexp plan` stops at the frozen plan + report, and passing
`--execute` only prints a notice.

The production entry point is `molexp.harness.PlanOrchestrator`. For the
internals, see the [Plan Mode architecture](../architecture/plan-mode.md).

## Prerequisites

```bash
pip install "molexp[agent]"
molexp config set agent.model anthropic:claude-sonnet-4-5
```

The model comes from `agent.model` in `~/.molexp/config.json` (CLI and server
share one loader). Override it per invocation with `--model`.

## Planning

```bash
molexp plan "Screen three solvent ratios and report conductivity"
molexp plan --file draft.md
```

| Stage | What you see |
|-------|--------------|
| Planning | The agent places tasks on the board through tools; it cannot finish while the form is incomplete |
| Review | Hard gate — approve / reject / revise (keep_tasks, notes, priority) |
| Freeze + report | The content-addressed frozen plan and a readable report land on disk |

Without a TTY grant and without `--yes`, the review gate **suspends** into the
approvals inbox; once granted, the same run resumes store-first. The default
project/experiment is `plans` / `plan`.

```bash
molexp plan --file draft.md --yes   # auto-approves the review gate; stops at the frozen plan + report
```

## UI

Switch the agent composer to **Plan** (mode pill or `Shift+Tab`). The same
`POST /plan-tasks` drives `PlanOrchestrator`.

- **Left rail** — the new stage list (task board → review → freeze → report → bind → source → compile…)
- **Right pane** — the current stage's deliverables
- **Approvals** — a structured form; **both approve and revise submit fieldValues**

## Artifacts

```text
runs/run-<id>/
├── plan/task_board.json
├── artifacts/
└── harness.sqlite
```

When realization goes all-green, the workflow IR is projected onto the
experiment so the graph viewer can open it.

## Approval actions

| Action | Effect |
|--------|--------|
| **Approve** | Writes the grant + optional field_values; on resume the plan is frozen and the report rendered |
| **Revise** | Applies field_values to the task board and re-enters the gate |
| **Reject** | The plan task is marked failed |

## Related

- Architecture: [Plan Mode architecture](../architecture/plan-mode.md)
- Tracked runs: [Tracked runs](../getting-started/tracked-runs.md)
