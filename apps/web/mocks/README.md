# Offline feature showcase

Run `npm run dev:web` from the repository root. The default project is Protein Folding. The mock is opt-in (`MOLAB_USE_MOCK=true`), uses MSW, and needs no Python server, SSH session, or user credentials. `npm run dev:api` continues to use the real API.

All content and job activity are synthetic. Refreshing the tab resets edits and actions. Dates are relative to startup so the dashboard's recent activity and schedule stay populated.

## What to explore

| Entry | Example | Features |
| --- | --- | --- |
| Dashboard `/` | 21 runs across three projects | Arc status instrument, recent activity, attention list, durations, backend breakdown, schedule |
| Projects `/projects/protein-folding` | AlphaFold Baseline, Structure Sweep | Experiment inventory, workflow graph and source, typed parameters, create run, project settings |
| Projects `/projects/nve-drift` | Integrator Benchmark | 12 driver × ensemble × timestep combinations, distinct numerical results, comparison and sweep instruments |
| Same project | Thermostat Validation | Empty experiment and unbound-workflow state |
| Runs `/runs` | Local and Molq executions | Filters, pagination, selection and cross-run comparison; queued, running, finalizing, succeeded, failed, interrupted and cancelled examples; one unexecuted run |
| Run `/projects/protein-folding/experiments/exp-001/runs/run-001` | Completed showcase | Executions, outputs, registered artifacts, evidence, journal graph, MolPlot scalars and Vega-Lite plot, Molq job details, TensorBoard, ΔF, MolVis discovery |
| Run `run-002` in the same experiment | Failed attempt followed by an active retry | Attempt timeline, per-attempt logs, cancellation |
| Run `run-003` in the same experiment | Failed attempt | Traceback, retry/resume/reproduce controls, harvest/failure-report flows |
| Assets `/assets` | Protein Folding → alphafold.pt | Two immutable version records, origin metadata, download; artifact promotion appends versions |
| Assets → NVE Drift | Water trajectory | XYZ bytes from the same execution file |
| Files `/workspace` | `projects`, `data`, `workflows`, `manuscript`, `managed-assets`, `knowledges` | Lazy folders, text/code/CSV/JSON, actual execution files, upload, byte-exact download, create and delete |
| Knowledge `/knowledge` | Eight documents | All six knowledge classes, Markdown editing, tags/status/search, entity links, missing-reference example, create/move/delete, media upload, Markdown and notebook ZIP export |
| Knowledge → Integrator benchmark.tex | Manuscript source and results table | BusyTeX source/preview entry |
| Settings `/settings` | Appearance, targets, remote descriptors, plugins | Theme/text-size controls, target and descriptor CRUD, test success/failure states, plugin preferences |

For comparison, add two or more runs to the selection from Runs or their individual pages. Expand an execution to inspect its products. Opening `run-001` discovers its plugin tabs from file names, just as a real workspace does.

## Fixture ownership

- `db/index.ts` owns projects, experiments, logical runs, canonical execution records, managed assets/versions, files and logs. Entity paths use display-name directories; IDs come from definitions rather than path parsing.
- Domain handlers implement the current generated API. `execution.ts` owns attempt operations and reads products from the same file tree the explorer uses. The old mock-only run execution, pre-parsed LAMMPS and rerun endpoints are removed.
- `workspaceRoute.ts` composes MSW's public `matchRequestUrl` with the explicit `/api/workspaces/feature-showcase/…` prefix, so comparisons and flat reads share resolvers and data.
- `workspace.ts` derives dashboard execution statistics from those canonical records. `molq.ts` derives queue jobs from the same Molq attempts; it does not maintain a second job fixture list.
- `feature_showcase.ts` owns document operations and the cross-domain read models. Unknown API operations still return an explicit 501 so missing coverage is visible.
- `fflate` is a development-only dependency used for real ZIP exports; exports contain the file bytes shown by previews.

The TensorBoard file is explicitly a synthetic discovery marker; the offline scalar endpoint serves deterministic samples, rather than claiming the marker is a parsed event file. Example model/data payloads are small illustrative files, not usable model weights or full scientific datasets.

## Limits

- MolVis's data and discovery routes are covered, but rendering still encounters the previously recorded external molvis/molrs export mismatch (`Cell` / `readStl`). This task does not modify those sibling packages.
- BusyTeX compilation requires its optional browser runtime assets; the seeded TeX source does not install that runtime.
- A physical attempt can be created and cancelled, but no scientific computation, scheduler submission or automatic progress is performed. Outputs of seeded attempts are fixed examples.
- The one served workspace is `/mock-workspace`. Adding another served root returns an explanation. Remote descriptors and tests are simulated configuration examples; authentication, SSH, HPC, real authorization and multi-workspace isolation require the real server. Auth is disabled in mock mode.
- Browser download and upload handlers preserve bytes, including binary data. Example initial payloads are intentionally small.

## Checks

`npm run test:web` exercises fixtures through MSW's public `getResponse`, including scoped reads, every seeded attempt/product, binary round-trips, ZIP contents, retry/cancel consistency, asset versions, knowledge export and linked queue jobs. `npm run typecheck:web` includes the mock database and handlers to catch drift against generated contracts.
