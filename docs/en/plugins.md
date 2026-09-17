# Writing a third-party molab plugin

## Scientific data vs plugins (dependency DAG)

**A molab Run is not a MolRec record.** The Run is a workspace *host*
(``run.json`` identity + hot state, run-root ``alive`` heartbeat, execution
``artifacts/``, ``source/``). Scientific packages are **MolRec** products
landed under the run or written beside it. Do not treat ``run.json`` as
MolRec ``status/`` / ``meta/``.

Latest molrec L4 (see molrec ``docs/spec/storage.md``):

```text
molrec (protocol)  — never imported; products follow the spec by convention
                      ↓
              molab / molvis / molplot  (the layers that obey and evolve it)
                      ↓
              molab Run (host: run.json + alive — not a Record)
                      ↓
   host metrics / plots (plugin activation by suffix):
     *.mlp.jsonl       live WAL under executions/<id>/artifacts/
     *.mlp.vl.json     Vega-Lite plot artifact
                      ↓
              UI plugins (filename match only — no protocol reimplementation):
                molplot ← *.mlp.jsonl / *.mlp.vl.json
                molvis  ← classic trajectories; *.mrec/
                          (plugin hands a directory source; molvis opens the store)
                molq    ← scheduler chrome only
```

**Record** 是 Zarr V3 根（文档段写在 group attributes；live metrics 是
``metrics/metrics.jsonl``，密化 series 在 ``metrics/`` 下）。科学包落到
``artifacts/`` 时遵循这套布局。**host** Run 不是 Record：``ctx.metrics``
写文件名门控的 ``*.mlp.*``，molplot 靠后缀激活、不必打开 Zarr。打开 Zarr
结构库是 **molvis**（molrs ``RecordReader``）的事，不是 molab UI 插件。
生产代码不要 ``import molrec``。

- **Core** Run UI lists products under **Outputs** and routes previews.
- **Plugins** activate only when filenames match — never hard-wired as core tabs.
- **Charts are molplot only** — training curves from ``*.mlp.jsonl``
  (same layout as molab ``ctx.metrics``). There is no
  separate metrics product package.
- Live append uses the **JSONL WAL** (``*.mlp.jsonl``). Leftover zarr/index
  files are ignored.
- Builtin agent ``run_land`` tags MolRec roots via the Zarr ``meta``
  attribute ``molrec_version`` (the record's sole version key) when present.

### Ingest foreign logs into the host metrics surface

Scientific packages may leave **LAMMPS logs**, **TensorBoard event dirs**, or
**CSV** tables beside a run. :mod:`molab.plugins.metrics_ingest` classifies
them by content and **normalizes** into the run-local metrics surface
(JSONL WAL at ``executions/<id>/artifacts/*.mlp.jsonl``).
Source files are never deleted or rewritten. A molab Run remains a **host** —
ingest does not write MolRec ``meta`` / ``status``.

```bash
# CLI (same core as the API)
molab runs ingest-metrics <project> <experiment> <run_id>
```

```http
GET  /api/projects/{p}/experiments/{e}/runs/{r}/metrics/detect
POST /api/projects/{p}/experiments/{e}/runs/{r}/metrics/ingest
```

Unrecognised files are skipped with a reason (never guessed). Missing optional
dependencies (e.g. TensorBoard) skip that format without failing the call.

---

Science adapters that the **plugin host** should see (molq jobs,
metrics writer) are duck-typed Host extras. The face (a CLI command, a
server route) constructs them with
:func:`molab.plugins.extras.default_science_extras` and passes
``compose_run(..., extra=…)`` / ``compose_plan(..., extra=…)``. The
**host** never reaches for ``molab.plugins`` itself — it composes what
it is handed. Inspect the tree with
``molab harness dump-config --profile run``.

Note that molab's own ``molab run`` needs none of this: the metrics
writer is wired onto ``molab.workspace.metrics_seam`` by ``import
molab``, so a plain workflow run produces its WAL with no plugin host
in the picture.

``PluginRegistry`` is only the leftover optional-dep cache (GitHub
client). It is not the host. Entry-point groups below are **face**
channels (CLI subcommands, UI bundles), not a second kernel.

molab ships **three completely independent** plugin channels so a
downstream Python package can extend molab without forking it or
re-bundling the frontend:

| Channel | What it adds | Runs in | Entry-point group |
|---|---|---|---|
| **CLI** | New subcommands under ``molab <yourcmd>`` | Python process at startup | ``molab.cli_plugins`` |
| **Server** | Routers on the ``/api`` surface + lifespan hooks | Python process, per ``create_app`` | ``molab.server_plugins`` |
| **UI** | Dynamic-imported React bundle in the SPA | Browser, on demand | ``molab.ui_plugins`` |

A package may contribute any of them, all of them, or none. The
channels do **not** share an entry point, a contract, or an API
version — they have completely different runtimes, lifecycles, and
evolution cadences, so they evolve independently.

> Why three? CLI lives in the Python process from boot and binds to
> Typer. Server binds to FastAPI and owns background work that has to
> be torn down with the app. UI lives in the browser, is fetched as ESM
> only when needed, and binds to the React contribution runtime. The
> only thing they have in common is that pip is the distribution
> channel — so each uses its own ``[project.entry-points]`` group in
> your ``pyproject.toml``.

**molab's own harness is the reference consumer of all three.** It
ships inside the molab wheel but attaches exactly the way a third-party
package would (`molab.harness.cli:CLI_PLUGIN`,
`molab.harness.server:SERVER_PLUGIN`) — nothing in molab core imports
it, and a plugin never reaches into another package's command tree or
schema module to attach itself.

## Adding a CLI command

A CLI plugin is a single :class:`molab.plugins.cli.CliPlugin` instance
referenced from the ``molab.cli_plugins`` entry-point group.

```toml
# pyproject.toml
[project]
name = "molab-plugin-greeter"
version = "0.1.0"
dependencies = ["molab", "typer"]

[project.entry-points."molab.cli_plugins"]
greeter = "my_plugin.cli:plugin"
```

```python
# my_plugin/cli.py
import typer

from molab.plugins.cli import CliPlugin


def _hello(name: str = "world") -> None:
    typer.echo(f"hello, {name}")


def _register(app: typer.Typer) -> None:
    app.command(name="greet")(_hello)


plugin = CliPlugin(
    id="greeter",
    name="Greeter",
    version="0.1.0",
    register=_register,
)
```

After ``pip install`` of this package alongside molab:

```bash
$ molab greet --name Alice
hello, Alice
```

### CLI contract

| Field | Type | Required | Purpose |
|---|---|---|---|
| ``id`` | ``str`` | yes | Globally unique short identifier |
| ``name`` | ``str`` | yes | Human-readable plugin name |
| ``version`` | ``str`` | yes | Plugin's own semver |
| ``register`` | ``Callable[[typer.Typer], None]`` | yes | Attach commands to the molab Typer app |
| ``api_version`` | ``str`` | no — defaults to ``"1"`` | CLI contract version targeted |

The instance is **frozen**. ``register`` has no ``None`` default — a
package without CLI contributions has no business in this group.

The current expected version is
``molab.plugins.cli.CLI_PLUGIN_API_VERSION``. Plugins targeting a
mismatched version are silently skipped at discovery time (logged as a
warning), and a single broken ``register`` call will not prevent the
rest of the CLI from booting — molab catches per-plugin exceptions
and keeps going.

## Adding server routes

A server plugin is a single :class:`molab.plugins.server.ServerPlugin`
instance referenced from the ``molab.server_plugins`` entry-point group.
``register`` receives the gated ``/api`` router; the lifespan hooks are
optional.

```toml
# pyproject.toml
[project.entry-points."molab.server_plugins"]
greeter = "my_plugin.server:SERVER_PLUGIN"
```

```python
# my_plugin/server.py
from fastapi import APIRouter

from molab.plugins.server import ServerPlugin

router = APIRouter(prefix="/greeter", tags=["greeter"])


@router.get("")
def hello() -> dict[str, str]:
    return {"hello": "world"}


def register(api: APIRouter) -> None:
    # Import your route modules *inside* register, not at module import:
    # merely discovering the plugin should not load your whole backend.
    api.include_router(router)


async def shutdown() -> None:
    """Cancel and await your in-flight background work."""


SERVER_PLUGIN = ServerPlugin(
    id="greeter",
    name="Greeter",
    version="0.1.0",
    register=register,
    shutdown=shutdown,
)
```

Your routes land on the same origin, the same port and the same session
cookie as the rest of ``/api``, and they appear in molab's OpenAPI
schema — so ``npm run generate:api`` picks them up like any other route.

Four optional hooks, in the order they fire:

| Hook | When | Sync/async | Use it for |
|---|---|---|---|
| ``register(api)`` | once, per ``create_app`` | sync | attaching routers |
| ``startup()`` | app startup | either | arming registries, pub/sub |
| ``signal_shutdown()`` | on SIGINT, **before** connection drain | sync only | waking SSE / long-poll generators |
| ``shutdown()`` | app shutdown | either | cancelling and awaiting background tasks |

``signal_shutdown`` exists because an SSE generator that is still
blocked on a queue will hold uvicorn in "Waiting for connections to
close" until every browser tab disconnects. Wake them there; do the
slow teardown in ``shutdown``.

Own your own wire, too: define the request/response models your routes
use in your own package. A plugin that has to add a class to molab's
``server/schemas/`` — or graft a subcommand onto molab's ``config``
group — is not using a seam, it is editing its host.

The current expected version is
``molab.plugins.server.SERVER_PLUGIN_API_VERSION``. Version mismatches
are skipped with a warning, and a ``register`` that raises is caught so
one broken plugin cannot take the whole API down.

## Adding a UI bundle

A UI plugin is just **a directory** that contains a pre-built ESM
bundle and a ``manifest.json`` describing it. Python's only role is to
tell molab's server where the directory lives — all UI semantics
(``id``, ``name``, ``version``, ``api_version``, entry point,
capabilities) are declared in ``manifest.json``, which is fetched by
the browser-side loader.

### 1. Declare the entry point

```toml
# pyproject.toml
[project.entry-points."molab.ui_plugins"]
greeter = "my_plugin.ui:bundle_dir"
```

The referenced symbol must be **either** a :class:`pathlib.Path`
**or** a zero-argument callable returning ``Path``. The
entry-point name (``greeter`` above) becomes the plugin id used in the
mount URL.

```python
# my_plugin/ui.py
from pathlib import Path


def bundle_dir() -> Path:
    """Return the directory containing manifest.json + index.js."""
    return Path(__file__).parent / "ui_dist"
```

### 2. Ship a ``manifest.json``

The bundle directory must contain a ``manifest.json`` at its root. The
schema (validated by the browser loader against
``UiBundleManifest`` in ``apps/web/src/plugins/types.ts``):

```json
{
  "id": "greeter",
  "name": "Greeter",
  "version": "0.1.0",
  "api_version": "1",
  "entry": "index.js",
  "capabilities": ["greeter"]
}
```

| Field | Type | Required | Purpose |
|---|---|---|---|
| ``id`` | ``string`` | yes | Must match the entry-point name |
| ``name`` | ``string`` | yes | Human-readable plugin name |
| ``version`` | ``string`` | yes | Plugin's own semver |
| ``api_version`` | ``"1"`` | yes | UI plugin contract version |
| ``entry`` | ``string`` | no — defaults to ``"index.js"`` | Filename of the ESM entry, relative to bundle root |
| ``capabilities`` | ``string[]`` | no | Free-form tags for downstream consumers |

The browser checks ``manifest.api_version`` against the
``UI_PLUGIN_API_VERSION`` constant frozen into the SPA build at compile
time. Bundles with a mismatched version are skipped (logged via
``console.warn``), and the rest of the SPA continues loading.

### 3. Ship a default-exporting ``index.js``

```javascript
// my_plugin/ui_dist/index.js
import { MolabPlugin } from "@molcrafts/molab-plugin";

export default class Greeter extends MolabPlugin {
  id = "greeter";
  name = "Greeter";
  version = "0.1.0";
  activate(api) {
    api.commands.register("hello", () => api.log.info("hello"), {
      title: "Say hello",
    });
    api.fileTypes.register({
      id: "greeter:run-tab",
      objectType: "run",
      value: "greeter",
      label: "Greeter",
      matcher: { patterns: ["*.greet.json"] },
      Component: () => null,
    });
  }
}
```

The bundle must be a valid native ESM module. Default-export
``{ id, activate(api) }`` (or a ``MolabPlugin`` subclass). The v1
``register()``-only shape still works for one compatibility version.

**Do not import ``@/app/registry``.** Contribute through ``PluginAPI``
domains (``commands``, ``views``, ``editors``, ``inspectors``,
``panels``, ``statusBar``, ``settings``, ``fileTypes``, ``entityTabs``,
``execution``, ``filePreviews``).

**Externalize host modules** with ``pluginExternals`` from
``@molcrafts/molab-plugin/externals`` (``react``, ``react-dom``, jsx
runtimes, ``@molcrafts/molab-plugin``, ``@molcrafts/molab-plugin/ui``).
The host injects a single React / SDK instance. Do not ship a second copy.

### How it gets served

molab's FastAPI server discovers your bundle via the entry-point
group, mounts the directory at ``/api/plugins/<id>/``, and surfaces the
descriptor through ``GET /api/plugins`` as
``{id, manifestUrl: "/api/plugins/<id>/manifest.json", entryUrl:
"/api/plugins/<id>/index.js"}``. The browser loader then:

1. fetches ``manifestUrl`` and validates the body;
2. checks ``manifest.api_version`` matches the build constant;
3. dynamic-imports ``entryUrl`` (or the override from
   ``manifest.entry``), rewrites bare host specifiers to the host
   singletons, and calls ``activate(api)`` on the default export
   (or the v1 ``register()`` shim).

Per-plugin failures at every step are isolated with ``console.warn``
so a single broken bundle cannot prevent other plugins from loading.

## Why the channels are independent

All three channels are discovered through Python ``importlib.metadata``
entry points, but **that's the only similarity**.

- They live in different runtimes (Python process vs. browser) and, for
  CLI vs. server, different frameworks (Typer vs. FastAPI).
- They load at different times (process startup vs. ``create_app`` vs.
  browser idle tick).
- They depend on different libraries (Typer vs. FastAPI vs. React + your
  bundler).
- Their API versions evolve on different cadences.
  ``CLI_PLUGIN_API_VERSION``, ``SERVER_PLUGIN_API_VERSION`` and
  ``UI_PLUGIN_API_VERSION`` are independent constants — bumping one does
  not force the others.
- Python carries **zero** UI semantics: no ``UiPlugin`` dataclass, no
  ``api_version`` field, no manifest parsing. UI semantics live in
  TS-side types and the bundle's ``manifest.json``. Python is the
  distribution shim only.

This separation is deliberate: a single ``MolabPlugin`` mega-class
that bundled all three would force a Python release just because the UI
manifest schema changed (or vice versa), which is exactly the wrong
coupling.

## Failure isolation

Every callback you provide runs inside a try/except (Python) or
try/catch (TypeScript) frame. A single broken plugin will not prevent
molab itself from starting, nor will it block other plugins from
loading. Failures are logged as warnings; if your plugin disappears,
check ``stderr`` (Python) or the browser console (UI) for a
``[plugins]`` line.

## Security boundary

**Plugins run in the host molab process with full privileges.** The
mechanism is a discovery convention, not a sandbox: there is no
permissions model, no per-plugin filesystem jail, and no network
restriction. Treat plugin packages exactly the way you would treat any
other PyPI dependency:

* only install plugins from sources you trust;
* pin versions in your environment so a compromised release of a
  plugin you already trust cannot silently auto-upgrade;
* review the CLI ``register`` callable and the UI ``index.js`` before
  deploying a new plugin to a production workspace.

If you need stronger isolation (e.g. for hosted multi-tenant
deployments), run molab itself in a confined process and treat the
plugin allowlist as part of your deployment manifest.

## Built-in plugins are not third-party

molab ships a few in-tree **UI** plugins (``core``, ``metrics``,
``molq``, ``molvis``) that are statically imported by ``App.tsx`` and
live inside the main bundle. They do **not** appear in
``GET /api/plugins`` and do **not** participate in the entry-point
discovery described here. Conversely, third-party packages cannot use
those reserved ids. The two paths run side-by-side without conflict.

The **harness** is the opposite case and worth studying: it also ships
in the molab wheel, but it is discovered through the entry points like
anything else (``molab.harness.cli:CLI_PLUGIN`` and
``molab.harness.server:SERVER_PLUGIN``). Nothing in molab imports it
by name — `tests/test_import_direction.py` fails the build if anything
does — so ``molab plan`` / ``agent`` / ``curate`` / ``harness`` and the
whole ``/api/agent*`` + ``/api/approvals`` surface exist exactly when the
harness is installed. If you are writing a plugin of your own, read it as
the worked example.
