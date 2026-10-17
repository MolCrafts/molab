<div align="center">

<h1>
  <img src=".github/assets/moko.svg" alt="" height="48" align="absmiddle">
  &nbsp;molab
</h1>

<p><strong>A scientific-workflow platform for FAIR research</strong></p>

<p>
  <a href="https://img.shields.io/github/actions/workflow/status/MolCrafts/molab/test.yml?style=flat-square&logo=githubactions&logoColor=white&label=test"><img src="https://img.shields.io/github/actions/workflow/status/MolCrafts/molab/test.yml?style=flat-square&logo=githubactions&logoColor=white&label=test" alt="test"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/license-BSD--3--Clause-18432B?style=flat-square" alt="License">
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square" alt="Ruff"></a>
</p>

<p>
  <a href="docs/en/index.md"><b>Documentation</b></a> &nbsp;&middot;&nbsp;
  <a href="#quick-start"><b>Quick start</b></a> &nbsp;&middot;&nbsp;
  <a href="#molcrafts-ecosystem"><b>Ecosystem</b></a>
</p>

</div>

molab turns a Python script of typed tasks into a tracked, reproducible experiment. It pairs a content-hashed workflow engine with a file-system-backed `Workspace → Project → Experiment → Run` hierarchy, profile-driven run variants, and optional cluster submission — then adds a knowledge layer that writes findings, reports and notes beside the runs they describe, and a FastAPI server with a bundled React UI.

> **Under active development.** Public APIs may change between minor releases.

## Vision

Research computation is rarely a single program — it is the same idea run many times, with different parameters, on different machines, until something works. The artifacts of that effort usually scatter: a script in one place, its outputs in another, the parameters in a notebook, the "which run was the good one" in someone's memory. molab exists to close that gap, so the definition of an experiment and the record of every execution are one connected object instead of folklore.

It aspires to make reproducibility the default rather than a discipline. You write ordinary typed Python; molab captures the workflow's content hash, the resolved configuration, the artifacts, the errors, and the execution history, and writes them down atomically as the run happens. The same workflow runs locally for a smoke test and on a cluster for the real thing, without changing the science — only where the worker process launches.

What that unlocks is a research workflow you can trust and revisit: experiments that re-run exactly, runs that can be compared and resumed, and a workspace that stays browsable — from the CLI or a web UI — long after the original author has moved on.

## Capabilities

| Module | Capability |
|--------|------------|
| `molab.workflow`   | Typed task-graph engine — `WorkflowCompiler` (decorator + OOP + protocol styles) compiles to a frozen, content-hashed `CompiledWorkflow`; `WorkflowRuntime` executes it with topology-driven parallelism, IR export, contract validation |
| `molab.workspace`  | File-system storage primitive — `Workspace → Project → Experiment → Run` `Folder` hierarchy, content-addressed assets, atomic JSON I/O, run lifecycle |
| `molab.config`     | In-code process-global config — a live `molcfg.Config` kept as a process-level place to register runtime values in code (never from env) |
| `molab.profile`    | File-based per-run config — `molcfg.yaml` loading and named profiles; resolves `defaults` + `profiles` into an immutable, content-hashed `ProfileConfig` |
| `molab.services`   | Application-service layer between the shells and the domain layers — `operator_config` (read / write `~/.molab/config.json`), `run_failure`, `auth`. CLI and server both call it and never each other, so a Python operation and a UI operation share one code path |
| `molab.knowledge`  | Knowledge documents (`knowledges/<slug>.md`, path is identity) and the `@concept_type` registry — sits above `workspace` and reaches it only through function-body imports |
| `molab.server`     | FastAPI app — REST routes for workspace, projects, experiments, runs, assets, execution, plus SSE streaming and bundled-SPA serving |
| `molab.cli`        | `molab` command-line entry point — workspace init/info, run/execute, project / experiment / run / asset / target / session subcommands |
| `molab.plugins`    | On-demand capability registry — `submit_molq` scheduler bridge (SLURM / PBS / LSF) and `gh` GitHub client; core stays dependency-light |
| `molab.git`        | Thin async wrappers over the `git` binary — `ensure_clone` / `fetch` / `push` and `GitWorktreeManager` for per-experiment working dirs |
| `apps/web/`         | React 19 + Rsbuild three-panel web client — navigation tree, entity viewers, inspector; compiled ahead of time and bundled into the wheel |
| `apps/vsc-ext/`     | VS Code workflow-preview extension — reuses the web workflow canvas components |

## Install

Distribution name on PyPI will be **`molcrafts-molab`** (CLI / import: `molab`). The former name `molexp` is retired — do not install it. Until the first publish, install from GitHub:

```bash
pip install "git+https://github.com/MolCrafts/molab"
# or, with uv
uv pip install "git+https://github.com/MolCrafts/molab"
```

Existing workspaces that still have `.molexp/` or `~/.molexp` must run `molab migrate brand` once before using this release.

Requires Python >= 3.12. Core depends on `pydantic`, `pyyaml`, `typer`, `rich`, `fastapi`, `uvicorn`, `zarr`, and the MolCrafts libraries `mollog`, `molcfg`, `molq`, and `molpy` (the workflow engine is self-owned — `pydantic-graph` is no longer a dependency). Optional extras: `molcrafts-molab[tensorboard]` adds the TensorBoard scalar reader; `molcrafts-molab[all]` bundles the optional extras, and `molcrafts-molab[dev]` pulls everything for development.

Default `uv pip` / `pip` **does not** compile the React UI (no Node required). A published wheel already ships `src/molab/dist/`.

## Serve the UI

Three jobs — do not mix them. Full table: [Serve and rebuild the UI](docs/en/development/ui-serve.md).

| Job | Command | Open |
|-----|---------|------|
| Daily checkout (HMR) | `uv pip install -e ".[dev]"` once, then `molab serve --dev -ws ./lab` | printed **Dev UI** (`:5173`) |
| Bundled SPA preview | `npm run build:web` then `molab serve -ws ./lab` | `:8000` |
| Wheel with UI | `uv pip install . -C build-web=true` | then `molab serve` on `:8000` |

`--dev` starts `npm run dev:api` (real `/api` proxy). `npm run dev:web` is the MSW mock, not that path. After `npm run build:web` on an editable install, do **not** reinstall Python. The old flag `-C build-ui=true` is rejected.

## Quick start

```python
import asyncio

from molab.workflow import Workflow, WorkflowCompiler, WorkflowRuntime

wf = Workflow(name="demo")


@wf.task
async def fetch() -> list[float]:
    return [1.0, 4.0, 9.0]


# A task receives an upstream's output by naming a parameter after that task —
# ``reduce`` binds ``fetch``'s output to its ``fetch`` argument (there is no
# ``ctx.inputs``: inputs are plain named parameters).
@wf.task(depends_on=["fetch"])
async def reduce(fetch: list[float]) -> float:
    return sum(fetch)


result = asyncio.run(WorkflowRuntime().execute(WorkflowCompiler().compile(wf)))
print(result.outputs)  # {'fetch': [1.0, 4.0, 9.0], 'reduce': 14.0}
```

Attaching a workflow to a tracked `Workspace` experiment (`ws.add_project(...).add_experiment(...).define(WorkflowCompiler().compile(wf), params=...)`), running it with `molcfg` profiles via `molab run`, and submitting to a cluster are covered in the docs.

## Documentation

- [Getting Started](docs/en/getting-started/index.md) — runnable first workflow, tracked runs, CLI and profiles
- [Concepts](docs/en/concept/index.md) — the workflow / workspace / plugin mental model
- [Guide](docs/en/guide/index.md) — task & actor authoring, runtime, assets, server, molq
- [Architecture](docs/en/architecture/index.md) — layer boundaries the code preserves
- [Development](docs/en/development/index.md) — serve/rebuild the UI, compiler internals, task protocols

## MolCrafts ecosystem

| Project | Role |
|---------|------|
| [molpy](https://github.com/MolCrafts/molpy)     | Python toolkit — the shared molecular data model & workflow layer |
| [molrs](https://github.com/MolCrafts/molrs)     | Rust core — molecular data structures & compute kernels (native + WASM) |
| [molpack](https://github.com/MolCrafts/molpack) | Packmol-grade molecular packing (Rust + Python) |
| [molvis](https://github.com/MolCrafts/molvis)   | WebGL molecular visualization & editing |
| **molab** | Scientific-workflow platform for FAIR research — this repo |
| [molnex](https://github.com/MolCrafts/molnex)   | Molecular machine-learning framework |
| [molq](https://github.com/MolCrafts/molq)       | Unified job queue — local / SLURM / PBS / LSF |
| [molcfg](https://github.com/MolCrafts/molcfg)   | Layered configuration library |
| [mollog](https://github.com/MolCrafts/mollog)   | Structured logging, stdlib-compatible |
| [molhub](https://github.com/MolCrafts/molhub)   | Molecular dataset hub |
| [molmcp](https://github.com/MolCrafts/molmcp)   | MCP server for the ecosystem |
| [molrec](https://github.com/MolCrafts/molrec)   | Atomistic record specification |

## Contributing

Contributions are welcome — see the [development docs](docs/en/development/index.md) (including [serve and rebuild the UI](docs/en/development/ui-serve.md)) to get started.

## License

BSD-3-Clause — see [LICENSE](LICENSE).

<hr>

<div align="center">
<sub>Crafted with 💚 by <a href="https://github.com/MolCrafts">MolCrafts</a></sub>
</div>
