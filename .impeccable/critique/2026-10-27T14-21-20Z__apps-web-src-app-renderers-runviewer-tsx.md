---
target: run page (RunViewer, Overview, Executions)
total_score: 24
max_score: 40
na_heuristics:
p0_count: 0
p1_count: 3
target_identity: "file:/nobackup/proj/disk/teoroo/personal/jicli594/work/molcrafts/molab/apps/web/src/app/renderers/RunViewer.tsx"
target_fingerprint: "sha256:b858f708c1b4e8f46c040a34fa446f650465c922e64cae988da946ce62ccd5aa"
target_path: /nobackup/proj/disk/teoroo/personal/jicli594/work/molcrafts/molab/apps/web/src/app/renderers/RunViewer.tsx
timestamp: 2026-10-27T14-21-20Z
slug: apps-web-src-app-renderers-runviewer-tsx
---
Method: dual-agent (A: 01a17db6-d396-7250-bca6-328b724d23ef · B: 01a17db6-d396-7250-bca6-329e34e3422c)

## Design Health Score

Target: run page (`RunViewer`, `RunOverview`, `RunExecutionsPanel`, `RunExecutionOutputs`). Mode: Operate.

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | A failed attempt shows a badge. The attempt `error` and the failed task are not on the surface you land on. |
| 2 | Match System / Real World | 3 | Modes, checkpoints, and the definition hash match the lab. "Realize this Run definition" and "StdIO" do not. |
| 3 | User Control and Freedom | 2 | The Ban control appears for `queued`, then `canCancel` returns before confirm because it allows only `running`. |
| 4 | Consistency and Standards | 3 | `EntityPage` and `OverviewSheet` match the experiment page. The Executions tab repeats an "Executions" heading. |
| 5 | Error Prevention | 3 | Disabled create-modes explain themselves. The confirm button is labeled "Cancel", the same word as leaving the dialog. |
| 6 | Recognition Rather Than Recall | 2 | The attempt button's accessible name is only "Select execution eNN", so status, mode, and duration disappear for assistive tech. |
| 7 | Flexibility and Efficiency | 2 | No jump from a failed row to that task's stderr or `out/<task>`. Outputs sit under a 420px graph inside another fixed frame. |
| 8 | Aesthetic and Minimalist Design | 3 | Overview is a quiet canvas. The execution pane still stacks two large bordered regions. |
| 9 | Error Recovery | 2 | A run-level `errorMessage` and a graph load error recover. An output load error is one red sentence with no retry. "No workflow snapshot." names no next file. |
| 10 | Help and Documentation | 2 | The create dialog explains each mode. "No parameters" and "No workflow snapshot." do not teach the next action. |
| **Total** | | **24/40** | **Acceptable** |

Cognitive load: 6 of 8 checklist items fail (single focus, chunking, visual hierarchy, one thing at a time, working memory, progressive disclosure). Grouping passes. Resting choices stay within four until plugin tabs attach. The create dialog is a separate decision point with four modes plus bypass cache, target, and an optional checkpoint id. 6 failures is high load.

## Design Specificity Verdict

**LLM assessment.** This page is authored for molab. It knows an attempt versus a run, a shared attempt timeline, resume versus rerun, a definition hash, and a journal graph. It is not a generic admin template. The weak part is composition, not costume: a one-attempt failure still opens as a census ("1 execution" plus a badge), and the file the person came for sits under a fixed graph. The quiet VS Code palette, status badges, and mono identifiers belong to this product. Icon-only toolbar actions are the committed workbench pattern (each has an accessible name and a hover title), so they are not a slop tell.

**Deterministic scan.** `impeccable detect` on the four run-page files exited 0 and returned `[]`. No rule hits. The detector did not see the dead Ban control, the fixed 420px graph, or the repeated heading, because those are behavior and hierarchy, not markup antipatterns. No false positives to reject.

**Visual overlays.** No overlay. This session has no browser automation tool and no CDP port, so the live-server inject step was not started.

## Overall Impression

The split between the attempt list and one execution is the right structure, and the order workflow-then-outputs matches the request. The page still answers "how many attempts" before it answers "what failed and what did it write." That is the single biggest opportunity.

## What's Working

- `AttemptBar` puts every attempt of one run on one time axis, so a slower retry is read, not calculated.
- `StatusLedger` appears only when there is a mix of attempts, and the rate is finished-work success, the same sheet shape as the experiment overview.
- Create-execution options carry disabled reasons. Reproduce forces bypass-cache. Adding the run to a comparison pins the attempt on screen, not "latest".

## Priority Issues

**[P1] A failed attempt does not lead with its error or its failed task.**
Why it matters: the person who opens a red run wants the first broken task and the first line of its log. Overview prints `run.errorMessage` only. The attempt record's `error` is never rendered. The executions header is id, badge, mode, and times. The node error, when the graph loads, is a tooltip.
Fix: on a non-succeeded attempt, put the error text and the failed task id above the graph, and select that task's stderr or `out/<task>` in the outputs pane.
Suggested command: `/impeccable clarify`

**[P1] The workflow and the outputs are two fixed frames stacked in one scroll.**
Why it matters: `WorkflowGraph` is `height={420}` inside an extra border, then `RunExecutionOutputs` is `h-chart-lg`. The file is below the fold, then clipped again. The list and the detail scroll separately, which is good, and then the detail throws that away.
Fix: let the detail column fill the viewport, graph and outputs side by side or with the graph height taking the leftover space, and drop the outer border around the graph.
Suggested command: `/impeccable layout`

**[P1] Stop shows for a queued attempt and then does nothing.**
Why it matters: `RunToolbar` sets `canCancelSelected` for `queued` or `running`. `handleCancelRun` bails when `canCancel` is false, and `canCancel` is running-only, before the confirm dialog. A queued job is exactly the attempt a person needs to stop. The confirm button is also labeled "Cancel", which is the word for dismissing the dialog.
Fix: one predicate for the button and the handler, include queued, and label the confirm "Stop eNN".
Suggested command: `/impeccable harden`

**[P2] The Executions tab repeats itself, and the selected attempt is hard to see and hard to hear.**
Why it matters: the tab already says `Executions (n)`. The pane adds another "Executions" heading, which the design system forbids for an inventory the tab already named. The selected row is `bg-accent/5`, close to the hover wash. The row button's `aria-label` replaces the visible status, mode, and duration. `AttemptBar` is `aria-hidden`, so the shared timeline has no text alternative.
Fix: remove the inner heading, mark the active row with the same selected wash used on inventory rows elsewhere (`bg-accent/5` is too faint here; use the list-selected treatment already used in the runs table, with a visible focus ring), and set the button name from the visible row.
Suggested command: `/impeccable quieter`

## Persona Red Flags

**Alex (power user).** No path from a failed row to that attempt's log. Create, Stop, Harvest, and Open workflow are icon-only; the names exist on hover and for assistive tech, but a fast pass still hunts. More hides Export run and Copy run ID. Many attempts are one unscannable list, with no failed-only filter. A failed attempt's default create mode is Rerun, so a fast confirm recomputes instead of resuming.

**Sam (keyboard and screen reader).** The executions row button announces "Select execution eNN" and drops the badge. The timeline bar has no text alternative. Tab triggers use `focus-visible:ring-0`. The flowgram node error is a tooltip. Reaching stderr means leaving the graph, remembering the task name, and finding it again under Outputs.

**Riley (stress tester).** Queued plus the Ban icon looks like stop and is a no-op. Refresh mid-run keeps the latest attempt only when the run id or the latest id changes; a manually selected older attempt survives that, which is correct, but a running duration is `Date.now()` at render and does not tick. "No workflow snapshot." and a failed outputs fetch leave the pane with no retry and no pointer to `run.log` or `traceback.txt`. An empty history says "Create an execution to realize this Run definition," which names an action in words a new reader has to translate.

## Minor Observations

- Missing duration still renders an em dash in `AttemptBar`.
- The detail header repeats the list index as `#n` next to the id.
- Artifact `semanticType` is micro uppercase.
- Promote uses the same Archive icon as the Artifacts folder, with no confirm and no visible failure.
- The Molq tab repeats executor fields already in the Executor list. Cluster and scheduler job stay conditional. There is no invariant "Backend: molq" row.
- `KnowledgeBacklinksCard` stays off the page when empty. That is correct.

## Questions to Consider

- If the usual run has one failed attempt, why does Overview lead with "1 execution" instead of the failed task's name and the first line of its log?
- Who is the 420px graph for on the day the question is "what did this task write"?
- On a failed attempt, should the primary verb be Resume, and should stopping an attempt say "Stop" so it does not share a label with dismissing the dialog?
