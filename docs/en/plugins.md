# Writing a third-party molexp plugin

## Scientific data vs plugins (dependency DAG)

**A molexp Run is not a MolRec record.** The Run is a workspace *host*
(``run.json`` identity + hot state, run-root ``alive`` heartbeat, execution
``artifacts/``, ``source/``). Scientific packages are **MolRec** products
landed under the run or written beside it. Do not treat ``run.json`` as
MolRec ``status/`` / ``meta/``.

Latest molrec L4 (see molrec ``docs/spec/storage.md``):

```text
molrec (protocol)  — never imported; products follow the spec by convention
                      ↓
              molexp / molvis / molplot  (the layers that obey and evolve it)
                      ↓
              molexp Run (host: run.json + alive — not a Record)
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
结构库是 **molvis**（molrs ``RecordReader``）的事，不是 molexp UI 插件。
生产代码不要 ``import molrec``。

- **Core** Run UI lists products under **Outputs** and routes previews.
- **Plugins** activate only when filenames match — never hard-wired as core tabs.
- **Charts are molplot only** — training curves from ``*.mlp.jsonl``
  (same layout as molexp ``ctx.metrics``). There is no
  separate metrics product package.
- Live append uses the **JSONL WAL** (``*.mlp.jsonl``). Leftover zarr/index
  files are ignored.
- Builtin agent ``run_land`` tags MolRec roots via the Zarr ``meta``
  attribute ``molrec_version`` (the record's sole version key) when present.

### Ingest foreign logs into the host metrics surface

Scientific packages may leave **LAMMPS logs**, **TensorBoard event dirs**, or
**CSV** tables beside a run. :mod:`molexp.plugins.metrics_ingest` classifies
them by content and **normalizes** into the run-local metrics surface
(JSONL WAL at ``executions/<id>/artifacts/*.mlp.jsonl``).
Source files are never deleted or rewritten. A molexp Run remains a **host** —
ingest does not write MolRec ``meta`` / ``status``.

```bash
# CLI (same core as the API)
molexp runs ingest-metrics <project> <experiment> <run_id>
```

```http
GET  /api/projects/{p}/experiments/{e}/runs/{r}/metrics/detect
POST /api/projects/{p}/experiments/{e}/runs/{r}/metrics/ingest
```

Unrecognised files are skipped with a reason (never guessed). Missing optional
dependencies (e.g. TensorBoard) skip that format without failing the call.

---

Science adapters that the **plugin host** should see (molq jobs,
metrics writer) are duck-typed Host extras. CLI and server construct
them with :func:`molexp.plugins.extras.default_science_extras` and pass
``compose_run(..., extra=…)`` / ``compose_plan(..., extra=…)``. Harness
never imports ``molexp.plugins``. Inspect the tree with
``molexp config dump --profile run``.

``PluginRegistry`` is only the leftover optional-dep cache (GitHub
client). It is not the host. Entry-point groups below are **face**
channels (CLI subcommands, UI bundles), not a second kernel.

molexp ships **two completely independent** plugin channels so a
downstream Python package can extend molexp without forking it or
re-bundling the frontend:

| Channel | What it adds | Runs in | Entry-point group |
|---|---|---|---|
| **CLI** | New subcommands under ``molexp <yourcmd>`` | Python process at startup | ``molexp.cli_plugins`` |
| **UI** | Dynamic-imported React bundle in the SPA | Browser, on demand | ``molexp.ui_plugins`` |

A package may contribute either channel, both, or neither. The two
channels do **not** share an entry point, a contract, or an API
version — they have completely different runtimes, lifecycles, and
evolution cadences, so they evolve independently.

> Why two? CLI lives in the Python process from boot and binds to
> Typer. UI lives in the browser, is fetched as ESM only when needed,
> and binds to the React contribution runtime. The only thing they
> have in common is that pip is the distribution channel — so each
> uses its own ``[project.entry-points]`` group in your
> ``pyproject.toml``.

## Adding a CLI command

A CLI plugin is a single :class:`molexp.plugins.cli.CliPlugin` instance
referenced from the ``molexp.cli_plugins`` entry-point group.

```toml
# pyproject.toml
[project]
name = "molexp-plugin-greeter"
version = "0.1.0"
dependencies = ["molexp", "typer"]

[project.entry-points."molexp.cli_plugins"]
greeter = "my_plugin.cli:plugin"
```

```python
# my_plugin/cli.py
import typer

from molexp.plugins.cli import CliPlugin


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

After ``pip install`` of this package alongside molexp:

```bash
$ molexp greet --name Alice
hello, Alice
```

### CLI contract

| Field | Type | Required | Purpose |
|---|---|---|---|
| ``id`` | ``str`` | yes | Globally unique short identifier |
| ``name`` | ``str`` | yes | Human-readable plugin name |
| ``version`` | ``str`` | yes | Plugin's own semver |
| ``register`` | ``Callable[[typer.Typer], None]`` | yes | Attach commands to the molexp Typer app |
| ``api_version`` | ``str`` | no — defaults to ``"1"`` | CLI contract version targeted |

The instance is **frozen**. ``register`` has no ``None`` default — a
package without CLI contributions has no business in this group.

The current expected version is
``molexp.plugins.cli.CLI_PLUGIN_API_VERSION``. Plugins targeting a
mismatched version are silently skipped at discovery time (logged as a
warning), and a single broken ``register`` call will not prevent the
rest of the CLI from booting — molexp catches per-plugin exceptions
and keeps going.

## Adding a UI bundle

A UI plugin is just **a directory** that contains a pre-built ESM
bundle and a ``manifest.json`` describing it. Python's only role is to
tell molexp's server where the directory lives — all UI semantics
(``id``, ``name``, ``version``, ``api_version``, entry point,
capabilities) are declared in ``manifest.json``, which is fetched by
the browser-side loader.

### 1. Declare the entry point

```toml
# pyproject.toml
[project.entry-points."molexp.ui_plugins"]
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
import { MolexpPlugin } from "@molcrafts/molexp-plugin";

export default class Greeter extends MolexpPlugin {
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
``{ id, activate(api) }`` (or a ``MolexpPlugin`` subclass). The v1
``register()``-only shape still works for one compatibility version.

**Do not import ``@/app/registry``.** Contribute through ``PluginAPI``
domains (``commands``, ``views``, ``editors``, ``inspectors``,
``panels``, ``statusBar``, ``settings``, ``fileTypes``, ``entityTabs``,
``execution``, ``filePreviews``).

**Externalize host modules** with ``pluginExternals`` from
``@molcrafts/molexp-plugin/externals`` (``react``, ``react-dom``, jsx
runtimes, ``@molcrafts/molexp-plugin``, ``@molcrafts/molexp-plugin/ui``).
The host injects a single React / SDK instance. Do not ship a second copy.

### How it gets served

molexp's FastAPI server discovers your bundle via the entry-point
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

## Why CLI and UI are independent

Both channels are discovered through Python ``importlib.metadata``
entry points, but **that's the only similarity**.

- They live in different runtimes (Python process vs. browser).
- They load at different times (process startup vs. browser idle tick).
- They depend on different libraries (Typer vs. React + your bundler).
- Their API versions evolve on different cadences. ``CLI_PLUGIN_API_VERSION``
  and ``UI_PLUGIN_API_VERSION`` are independent constants — bumping one
  does not force the other.
- Python carries **zero** UI semantics: no ``UiPlugin`` dataclass, no
  ``api_version`` field, no manifest parsing. UI semantics live in
  TS-side types and the bundle's ``manifest.json``. Python is the
  distribution shim only.

This separation is deliberate: a single ``MolexpPlugin`` mega-class
that bundled both would force a Python release just because the UI
manifest schema changed (or vice versa), which is exactly the wrong
coupling.

## Failure isolation

Every callback you provide runs inside a try/except (Python) or
try/catch (TypeScript) frame. A single broken plugin will not prevent
molexp itself from starting, nor will it block other plugins from
loading. Failures are logged as warnings; if your plugin disappears,
check ``stderr`` (Python) or the browser console (UI) for a
``[plugins]`` line.

## Security boundary

**Plugins run in the host molexp process with full privileges.** The
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
deployments), run molexp itself in a confined process and treat the
plugin allowlist as part of your deployment manifest.

## Built-in plugins are not third-party

molexp ships a few in-tree plugins (``core``, ``metrics``, ``molq``,
``molvis``) that are statically imported by ``App.tsx`` and live
inside the main bundle. They do **not** appear in ``GET /api/plugins``
and do **not** participate in the entry-point discovery described
here. Conversely, third-party packages cannot use those reserved ids.
The two paths run side-by-side without conflict.
