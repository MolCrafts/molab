# Development

Contributor-facing docs for working on `molab` internals.

## UI

- [Serve and rebuild the UI](ui-serve.md) — daily `molab serve --dev`; bundled preview with `npm run build:web`; wheel only with `-C build-web=true`

## Internals

- [Compiler](compiler.md) — DSL → `CompiledWorkflow` → `ExecutionPlan` lowering + structural engine, identity, caching
- [Task Protocols](task-protocols.md) — `Runnable` / `Streamable` structural contracts

## CI and release

Each workflow's first job, `<file> / context`, runs
[`MolCrafts/molcrafts-ci/actions/ci-context`](https://github.com/MolCrafts/molcrafts-ci/tree/master/actions/ci-context);
every other job gates on its outputs (tier, upstream, pull request dedup).

| workflow | fast tier (a feature-branch push to MolCrafts) | full tier (every fork push; dev / master on MolCrafts; PRs, tags, dispatches) | upstream only |
|---|---|---|---|
| `lint.yml` | `lint / python` (partners, lock, ruff incl. PLW1514, ty), `lint / web` (biome, tsc), `lint / workflows` (`actions/check-workflows`) | same | — |
| `test.yml` | `test / context`, `test / python (ubuntu-latest)` (pytest), `test / web` (rstest) | + `test / python (macos-latest)` | — |
| `docs.yml` | `docs / build` (strict Zensical, en + zh) | same | — |
| `release.yml` | — | — | `v*` tag: `release / build`, `release / pypi` (PyPI, environment `pypi`); `workflow_dispatch` is a dry run anywhere |

CI builds molab against the commits pinned in `.github/partners.env`
(molpy, molrs, mollog, molcfg, molq, and `CI_REF` for molcrafts-ci), never
against published releases or a developer's own sibling checkouts.
`scripts/partners.py` bootstraps `molcrafts_ci.partners` at that `CI_REF` and
uses each ref exactly as written. CI checks them out as siblings, the layout
the `[tool.uv.sources]` path dependencies expect, and builds molrs from source.
The git hooks run ty, the lock check and the unit suite in the same layout
(`scripts/partners.py run`), so a local gate and CI judge the same commits.
The unit suite holds unit tests only: no speed, regression or end-to-end tests
(`tests/README.md`). A pull request inside a fork skips the jobs its push
already ran. Shared setup is `MolCrafts/molcrafts-ci/actions/<name>@<CI_REF>`,
the same commit as `CI_REF`. Windows is not a target
(termios, process groups). To release, bump `version` in `pyproject.toml`,
merge to master and push a `v*` tag; the PyPI trusted publisher must name
`release.yml` and the `pypi` environment.
