# Serve and rebuild the UI

Python install and UI compile are separate jobs. Default `pip` / `uv pip` /
`python -m build` **never** invoke npm. Pick one of the three paths below —
do not mix them.

## Daily development (checkout)

HMR against a real API. Rebuild neither the wheel nor `dist/`.

```bash
npm install                         # repo root, once
uv pip install -e ".[dev]"          # Python, once (reinstall only when Python deps change)

molab serve --dev -ws ./lab --port 8000
```

Open the printed **Dev UI** URL (default <http://localhost:5173>), not the
API port. `--dev` starts `npm run dev:api` and proxies `/api` to this
process.

`npm run dev:web` is the MSW mock showcase — it does not talk to a molab
server. Override the UI port with `--ui-port`, or the web tree with
`MOLAB_WEB_DIR`.

## Preview the bundled SPA

What a wheel user sees: one process, no Node at runtime.

```bash
npm run build:web                   # writes src/molab/dist/
molab serve -ws ./lab --port 8000  # open http://localhost:8000
```

An editable install reads the in-tree `src/molab/dist/`. After
`npm run build:web`, **do not** `uv pip install` again.

Empty `dist/` → API-only (`/api/docs`, `/api/health`). `create_app()` finds
the bundle via `importlib.resources.files("molab") / "dist"`.

## Ship a wheel

The only path that should pass `-C`:

```bash
uv pip install . -C build-web=true
```

That runs `npm run build:web` before setuptools packages `src/molab/dist/`.
The old flag `-C build-ui=true` is rejected. `src/molab/dist/` is
gitignored (except `.gitkeep`).

```
apps/web/src/  →  npm run build:web  →  src/molab/dist/  →  setuptools  →  wheel
```

From GitHub, a published wheel already contains the UI — no Node required:

```bash
uv pip install git+https://github.com/MolCrafts/molab
molab serve -ws ./lab --port 8000
```

## Spellings

| Use | Never |
|---|---|
| `npm run build:web` | `npm run build:ui` |
| `-C build-web=true` | `-C build-ui=true` |
| `molab serve --dev` / `npm run dev:api` | `npm run dev:web` against a real API |

## Related

- [Start from the UI](../getting-started/start-from-ui.md) — browser workflow for end users
- [Server Lifecycle](../guide/server-lifecycle.md) — auth, `--tunnel`, several workspaces, `ServerManager`
- [`apps/web/README.md`](../../../apps/web/README.md) — frontend scripts
