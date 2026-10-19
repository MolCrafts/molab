# molab remote access through molq

Status: implementation and local checks complete. Production Web bundling and real SSH/HPC acceptance remain open as agreed with the user. No legacy interfaces, configuration compatibility, migration tools or migration prompts.

## Ownership
molq owns registered destinations, generic authentication and bounded filesystem/transfer APIs. molab owns workspace authorization, semantic file selection, experiment records, cache policy and HTTP presentation. Shared deployments use one preconfigured service account; browser OTP remains supported by molq.

## Public contract
- All remote operations bind explicit registry/cluster identity. Stage-in, submit, stage-out and queries use the same destination. molab stores destination references and semantic paths, never SSH or scheduler definitions.
- Existing files.* and Path remain canonical. files.list gains with_stat/limit/after (256 default, 512 maximum); files.read_many accepts up to 128 paths, 256 KiB each and 512 KiB aggregate. Output stays within the 1 MiB frame. No silent truncation or per-file remote round trips masquerading as batch I/O.
- Optional root constraints reject traversal and escaping symlinks on the target. Add recursive remove, chmod, symlink and bounded transfer deadlines. Files do not instantiate Scheduler.
- connections.authenticate accepts a destination and one OTP; use one bounded attempt, private OpenSSH control paths and identical connection arguments for authentication and subsequent operations. Never expose codes in logs, argv, registry or configuration; do not close user masters. No ControlMaster prerequisite for key authentication.
- RemoteFileSystem becomes a public molq API adapter. A service-owned explicit stdio client is opened/closed with molab. No implicit client. Remote syntax follows molq.Path cluster:path.
- Cache keys include registry/cluster/root. Pinned cache refreshes explicitly; strict reads fetch content rather than treating equal size/mtime as proof of freshness.
- Web upload/download use bounded streams or disk staging. No whole-file buffering for large files. Preserve OUTCOME_UNKNOWN; never automatically resend mutations.

## Roadmap and evidence
- [x] R0: record baseline/spec and existing working-tree changes.
- [x] R1: root-boundary and destination-identity regressions/fixes.
- [x] R2: molq bounded generic APIs, target-side batches and generated contracts/SDKs.
- [x] R3: molq authentication plus accurate molab web states.
- [x] R4: molab destination models, API-only filesystem, semantic prefetch and cache; remove parallel implementations.
- [x] R5: web streams, transfers, deadlines and uncertain outcomes.
- [ ] R6: dependency pins, documentation, architecture guards and local re-audit implemented; production Web bundle acceptance remains blocked externally.

Each stage is a small verifiable batch. Preserve unrelated user changes and historical experiment data. Fail old configuration through ordinary new-schema validation; do not add compatibility paths.

## Acceptance
molq tests cover pagination, metadata, batch item errors/limits/one target request, scope and symlink escape, atomic replacement, mkdir combinations, transfers and failures, OTP cleanup and argument secrecy. molab tests cover semantic requests, consistent destination identity, cache freshness, HTTP streaming and authorization. Run repository lint/type/build/generated gates. Real Linux SSH/HPC/OTP and large-scale latency verification are separate from local fixture evidence and must not be claimed without an actual host.

## Baseline
Previous read-only audit: molab targeted suite 121 passed, 1 xfailed; molq Python path/transfer/architecture 6 passed; Go serve/transport/architecture passed on macOS. Both checkouts contained substantial preexisting uncommitted changes. The original molab MOLQ_REF was initially absent from the local molq object database; fetching upstream established that it points to the older 0.8.1 Python service, rather than the required 0.9 Go service. The integration pin below replaces that baseline.

## Implementation notes and local review

- molq owns scoped path resolution, bounded pagination/batches, chmod/symlink/recursive remove, transfer deadlines and one-response authentication. Generated sync/async/TypeScript contracts were regenerated from their existing sources. Native checks acquire cluster concurrency before target-side validation.
- molab's RemoteFileSystem uses the public SDK only. Removed OpenSsh, custom rsync/shell operations, fake transport/session ownership and the obsolete molq dashboard dependency. The terminal monitor reuses molab's TreeMonitor. CLI addresses resolve registered destination prefixes; browser forms choose registry destinations.
- Every submitted execution stores registry ID, canonical cluster ID and scratch root before staging. Reconciliation uses that snapshot even when the named target is removed or reconfigured. Uncertain submission/return transfer is retained and does not enter an automatic mutation retry loop.
- Cancellation and observation call the application-owned client directly with the stored JobRef registry. Removed the borrowed-client forwarding context manager and the CLI scheduler/default-cluster cancellation fallback. A missing JobRef produces a warning instead of guessing a destination.
- The Web service owns and closes an explicit stdio client. File listing, editor writes, directory creation, raw uploads and attachment downloads use the scoped FileSystem. Upload bodies stage on disk (8 GiB cap); downloads read at most 256 KiB per chunk. Workspace allowlists and role permissions apply to these routes.
- Cache identities include registry/cluster/root even with a custom cache directory. Pinned mirrors change on explicit refresh; strict reads refetch equal-size/same-second changes. Semantic project/experiment/run/execution metadata is primed through target-side batches. Raw payloads are not crawled merely to obtain a progress denominator.
- Review fixes: preserve symlink identity on unlink; merge hidden/ordinary directory windows in byte order; reserve encoded path/error overhead below the RPC frame cap; validate nested links for dereferencing transfers; distinguish authentication timeout from rejection/unreachable; propagate unknown transfer outcomes; reject cache-path traversal before mirror access.

## Integration pin and verification

molq commit: `4a3b306c0ab4d4e9dc9c6b646e10484587dec7fa`, pushed to
`Roy-Kid/molq` on `codex/molq-remote-access`. `.github/partners.env` pins that
repository and full commit. The fork is required because `MolCrafts/molq`'s
previous integration ref still contains the incompatible 0.8.1 implementation.
The pin was verified against the remote branch; builds do not resolve a moving
branch name. Other partner pins and unrelated checkout changes are preserved.

| Gate | Evidence |
|---|---|
| molq service | `CGO_ENABLED=0 go test ./...` passed, including the exact committed snapshot. |
| molq Python SDK | 173 tests passed, 88.09% coverage; lint, format and source type checks passed. |
| molq generated contracts | Existing contract/client generators and `tools/check_generated.py` passed. |
| molq TypeScript | 26 tests, build and type tests passed. |
| molq package | Wheel and sdist built; a fresh wheel installation passed packaged binary, CLI JSON and SDK execution checks. |
| molab Python | Final full suite: 2633 passed, 1 xfailed. Lint, format and source type checks passed. Cancellation/submission/CLI/stream regression batch: 245 passed, 1 xfailed; final cancellation/preview contracts: 18 passed. |
| molab Web | 743 tests passed; lint and TypeScript checks passed. OpenAPI and the existing generated client were refreshed. |
| molab package | Python-only wheel and sdist built. These do not include a production Web bundle. |
| molab documentation | 65 documentation checks passed; the destination example runs with the new value model. |
| Ownership | Architecture guard rejects molq service-internal imports and direct SSH/rsync command lists from molab; remote fixtures exercise public stdio RPC. |

During final checks, dependency synchronization temporarily installed the sibling
molrs build with a changed Python I/O contract under the same 0.18.0 version.
Reinstalling the published 0.18.0 dependency restored the preview and source type
checks; no preview compatibility implementation was added. This environment
failure is separate from the production Web blocker below.

The final Judicious review traced destination resolution, immutable execution
identity, scoped file/cache access, authentication/error mapping, transfer
publication and client cleanup across both repositories. It removed remaining
forwarding and cancellation fallback code, and updated the target example and
workspace architecture documentation. This review does not cover unrelated
preexisting UI/workflow changes in the molab worktree.

## Remaining acceptance

The user initially deferred real SSH/HPC/OTP acceptance on 2026-10-18, then requested a live check of `Arrhenius:/home/jicli594/work/lab/projects/nve-drift`. The live connection reaches Arrhenius and its configured public key is accepted with partial success; OTP authentication subsequently succeeded and read-only access verified the project marker, directory listing and 16 experiment entries. Local fake-SSH and stdio tests do not close that gate. Root checks are target-side operation constraints; they do not promise OS sandboxing against concurrent directory replacement by another process running as the service account. Windows OTP is not verified.

The user explicitly kept production Web bundling as an external blocker on
2026-10-18: existing molvis core/stage code requests exports such as `Cell` and
`readStl` that the installed molrs WASM package does not expose. No molvis source
was changed for this task. R6's production bundle gate remains open until those
packages agree. Python-only package success does not close that gate.

For eventual real-host acceptance, use a registered Linux SSH/HPC destination to
exercise key authentication, one-code OTP, scoped listing/batches, stage-in and
submission identity, reconciliation/cancellation, stage-out, directory layout,
large workspaces and large-file transfers. The current Arrhenius request authorizes connection and browsing; it does not
close the remaining job/transfer acceptance gates. Shared service-account authorization is the
deployment model; per-user SSH identity isolation is outside this release.

## Live authentication investigation

The first live attempt exposed two lossy error boundaries: molq discarded SSH stderr, and molab mapped every non-timeout authentication transport failure to `Host unavailable`. The existing transport error now carries a bounded diagnostic with the submitted response redacted before truncation. molab preserves that diagnostic and distinguishes authentication from post-authentication root access. Regression tests fail before the changes and pass afterwards; the full Go suite and relevant Python/Web checks pass. The live service is running on API port 8010 and development UI port 5180. A fresh user-entered OTP is required to obtain the specific SSH failure; no automatic authentication retries are performed.

### Repeated unauthenticated probe fix

The live SSH diagnostic reported `kex_exchange_identification: read: Connection reset by peer` before OTP exchange. Browser workspace-list/scope polling was repeatedly opening rejected SSH sessions because only successful roots were cached. The existing workspace cache now also owns compact remote-open failure values, without exception tracebacks or credential-bearing request frames. Concurrent initial opens share a lock; AUTH_REQUIRED waits for explicit authentication/cache reset, while network failures have a 60-second quiet interval. Healthy cached roots retain the fast path. Workspace responses set needsAuth only for actual authentication failures. New regressions fail before the fix (3 failed, 1 passed) and pass afterwards; all 241 server tests pass.

After stopping the repeated probes, one bounded banner check received `SSH-2.0-OpenSSH_9.9`, and the restarted service reached the authentication-required state. The connection-reset cause is not confirmed without Arrhenius server logs. Repeated incomplete SSH sessions are compatible with server-side startup/source limits documented in [OpenSSH sshd_config](https://man.openbsd.org/sshd_config#PerSourcePenalties); this remains an inference, not a verified HPC configuration. The next live step is a fresh user-entered OTP. No project contents or job/transfer behavior have been accepted yet.

### Canonical key in authentication prompts

A later live attempt returned HTTP 404 locally: flat active-root errors exposed the target descriptor name, while the authentication route requires the served-workspace key. The global 503 prompt used that descriptor as its request key, so the OTP was never forwarded. Active remote resolution now reuses `active_served_key()` when constructing its errors. A regression fails with `descriptor` before the fix and passes with `remote-descriptor` afterwards. The running service was checked directly: workspace-list key and scope-error authentication key now match exactly. Unexpected HTTP failures retain their message instead of becoming `failed`. Relevant Python regressions (22 tests), Web authentication regressions and both source type checks pass. Live root browsing still awaits a valid OTP; the prior 404 does not establish any remote authentication failure.


### Scoped Arrhenius project and connection chrome

The user completed OTP authentication successfully. The remote project root denies ancestor reads as designed; optional enclosing-workspace discovery now treats that denial as absence of an accessible parent and uses the existing parentless project loader. The root constraint remains enforced. Scope and workspace regressions pass (66 tests); live scope identifies `nve-drift` and the project reports 16 experiments. No remote mutations or job/transfer acceptance were performed.

Connection chrome follows the user-selected `SSH: Arrhenius` label. CLI and HTTP root composition use the registered destination name for display while retaining canonical registry/cluster IDs for operations. The status strip has one connection button, with path, state and reconnect in its popover; project names remain in the explorer tree and page. Idle heartbeat animation and duplicate connection/readiness text are removed.

Validation for the chrome change: 17 serve-scope tests, 27 focused Web tests, Python/Web source type checks and Web lint pass; the design detector reports no findings. The live UI shows `SSH: Arrhenius`, Connected and the correct root in its connection popover. Full experiment rendering is not yet accepted: the experiment-list request exceeded a bounded 12-second observation, and the project assets endpoint raises `AttributeError` because the existing asset repository assumes a parent Workspace with a `root` attribute. These data-loading problems are distinct from the completed connection-label cleanup.

### Loading fix and shallow remote navigation

The subsequent loading investigation traced project listing to `ExperimentResponse.from_model`: every experiment eagerly read every run to compute a navigation count. Shallow responses now use the existing nullable `runCount` contract; detail responses still supply exact counts and run rows. Only the listed experiments' workflow documents are primed through `CachedRemoteFileSystem.read_many` and the public molq batch API. Arrhenius returned all 16 experiments in a measured 0.92 seconds after this change, and the browser rendered the complete experiment table and explorer entries.

Remote hover/focus intent no longer starts project/run scans, and project assets are fetched only when the Assets tab is opened. Explicit clicks and expansion still load entity data. Failed experiment requests retain their error in the existing snapshot and render the shared retry/error UI instead of inferring an endless loading state from a stale count.

Parentless project asset and execution readers now use the existing `Folder.resolve` and `Folder.asset_host` contracts instead of assuming a parent Workspace. Run serialization reuses one execution snapshot for workflow, status and finished fields, reducing five history scans to one. Cached run and execution metadata is fetched through the existing bounded batch API. Execution discovery lists each attempts directory once and selects explicit execution.json paths, avoiding a separate listing inside every attempt directory. Regressions reproduce each old failure before its fix, including unexpected run traversal during shallow listing, batch RPC use, parentless project reads, duplicate execution scans and remote hover scans. No remote scientific files or historical records were rewritten.


Loading regression evidence: the focused failures are recorded in `/tmp/molab-loading-before.log`, `/tmp/molab-loading-batch-before.log`, `/tmp/molab-loading-runs-before.log`, `/tmp/molab-loading-snapshot-before.log`, `/tmp/molab-loading-hover-before.log` and `/tmp/molab-loading-execution-batch-before.log`. After the fixes, 107 filesystem/execution repository tests and 43 frontend tests pass, as do source type, lint and format checks. The current production Web build blocker and unperformed real job/transfer gates remain as documented above.


The live thread trace identified another eager scan: both App and NavigationRail called `useWorkspaceTabVisible`, which started the global runs poller even on project/experiment pages. The visibility hook now uses the existing `useWorkspaceRuns({enabled: false})` option; Dashboard/Runs remain the owners of active polling. The removed project overview had also left behind an effect that expanded runs for every experiment; that effect is deleted. An architecture regression prevents both navigation paths from reintroducing eager scans.

Live browser verification subsequently rendered all 36 runs in `proton-transport`, including execution state: 36 Completed, zero running/queued/failed/cancelled. The complete project list contains 16 experiments. Directory/history loading still costs remote round trips; this is verified read-only browsing, not a benchmark or completed large-workspace/job/transfer acceptance. Temporary trace instrumentation was removed from the running service. Final checks: 252 server tests, 107 filesystem/execution tests, 61 frontend tests, Python/Web source types, format and lint pass.


## Audit repair: worker context and shared deployment (2026-10-19)

Registry-wide molq jobs, destinations and logs require an unrestricted (`*`)
workspace grant when Web authentication is enabled. Workspace-limited users use
workspace-scoped surfaces. Queue queries fail explicitly on a failed destination
or incomplete scheduler coverage; a failed query is never a successful empty page.

Remote runs have a private namespace under `<scratch>/<workspace-id>/<project-id>/
<experiment-id>/<run-id>/`. Inside that namespace the original workspace-relative
run layout is preserved. Stage-in includes only the selected workspace/project/
experiment entity metadata, its workflow document or captured code, the run, and
the selected execution. Code locators are rebound through Experiment.bind_workflow
in a temporary staging copy. Original experiment files and execution records are
not rewritten. The existing Run.load and workflow recovery path therefore open the
staged run without a parallel worker loader. Code source uses the existing
source_manifest/copy_sources contract (flat first-party sibling closure); package
entrypoints ship their package. Third-party dependencies must be installed remotely.

Frontend server state belongs to the existing QueryClient. Connection switches
cancel previous queries, clear their cache, and remount the workspace UI; query
keys include the connection generation. Aggregate run row selections reuse the
existing composite RunRef identity, and inspector log requests name their workspace.


The submit operation freezes its resolved remote run path in the unsealed
Execution's operational executor metadata before any staging or scheduler call.
Stage-in and the worker command receive that same value, and stage-out uses it
rather than reconstructing a path from a possibly renamed local workspace.

### Audit closure evidence

The 13 audited findings are addressed in their existing owners:

| Finding | Owner / verification |
|---|---|
| 1 Registry authorization | `server/deps/auth.py`, molq router; restricted-user endpoint regressions |
| 2 Worker context | `submit_molq/staging.py`, `workspace/targets.py`; strict xfail promoted to normal, independent subprocess tests for file/package/captured source after originals are removed |
| 3 Workspace identity | existing compare RunRef keys, connection-scoped Query keys, named inspector logs; cloned run IDs select independently in browser |
| 4 Server-state ownership | workspace snapshot and runs singleton replaced with existing QueryClient; dependent refresh waits for fresh upstream queries |
| 5 Binary open | cache adapter preserves rb bytes and rejects write modes |
| 6 Cache consistency | mutation generation fences, protected pinned reads, ancestor/subtree eviction and existing atomicio publication; deterministic read/write, mkdir, nested parents and reopen regressions |
| 7 Download bounds | three routes use one range iterator; endpoint regressions forbid buffered open and check chunk bounds |
| 8 Authentication errors | cache reconnect retains native MolqError classification |
| 9 Async publication | Query owns in-flight results; directory merges update current cache; switching cancels previous connection queries |
| 10 Failed reads | required reads reject, entity errors remain visible, explicit refresh can retry failed deep directories |
| 11 Poll lifecycle | Query owns scheduling/cancellation; browser verifies hidden pause and visible resume; failed tree loads stop automatic retries |
| 12 Queue errors | one queue coverage check across list/health/detail; real dashboard-to-HTTP missing/partial regressions |
| 13 Dead implementation | unused private container prefetch implementation removed |

Verification, 2026-10-19:

- Initial focused Python baseline: 54 passed. Added cache regressions first reproduced
  four failures, then three mkdir/reopen failures, then two ancestor-creation failures;
  each batch passed after its fix. Server boundary regressions initially reproduced
  11 failures. Remote baseline: 69 passed, 1 strict xfail.
- Final `python -m pytest tests/ -q`: **2687 passed**, two existing zero-task workflow
  warnings. No xfail remains for the staged-worker scenario.
- Web baseline `npm run test:web`: **752 passed**; final: **758 passed**.
- `ruff check src/ tests/`, `ruff format --check src/ tests/`, `ty check src/`,
  Web TypeScript check, Web lint and `git diff --check` pass. Biome emits its
  pre-existing schema-version informational notice.
- OpenAPI was regenerated with the existing script; this repair adds no wire schema
  changes requiring different generated client types.
- Local mock browser checks: failed run fetch count stays at 2 after bounded retry;
  hidden aggregate poll count stays 1 and becomes 2 after visibility resumes;
  failed deep directory recovers on Refresh (2 -> 3 requests); cloned IDs in roots
  a/b have distinct selection URLs and only the selected root's row is highlighted.
- Production Web build still fails in external molvis/molrs imports (`Cell`,
  `readStl` and related interfaces), as the user explicitly deferred. Some seeded
  mock run output/file endpoints also return 501; browsing/layout and the injected
  boundary checks above do not establish those optional previews as working.
- No real SSH/HPC jobs or transfers were run in this repair. Those acceptance gates
  remain open; existing scientific data and historical executions were not migrated.
