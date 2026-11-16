<!-- mol:note:topic:ui-serve-build -->
# UI serve and rebuild

**Status:** live (2026-08-28). Public prose: `docs/en/development/ui-serve.md`.

**Rule:** Python install and UI compile are separate jobs. Default `pip` / `uv pip` / `python -m build` never invoke npm. Daily UI work is `molab serve --dev`; do not `uv pip install` to pick up frontend edits.

**Supersedes:** `npm run build:ui` / `-C build-ui=true` as spellings; treating `-C build-web=true` as the daily rebuild; opening the API port (`:8000`) as the HMR page.

## Three paths

| Job | Command | Open |
|---|---|---|
| Daily checkout (HMR) | `npm install` once; `uv pip install -e ".[dev]"` once; `molab serve ./lab --dev --port 8000` | Printed **Dev UI** (`:5173`) |
| Bundled SPA preview | `npm run build:web` then `molab serve ./lab --port 8000` | `:8000` |
| Wheel / non-editable | `uv pip install . -C build-web=true` then `molab serve ./lab` | `:8000` |

Editable installs read in-tree `src/molab/dist/` after `npm run build:web` — **do not reinstall Python**. Empty `dist/` → API-only; `create_app()` looks up `importlib.resources.files("molab") / "dist"`.

## Spellings

| Use | Never |
|---|---|
| `npm run build:web` | `npm run build:ui` |
| `-C build-web=true` | `-C build-ui=true` (setup.py exits) |
| `molab serve --dev` / `npm run dev:api` | `npm run dev:web` against a real API |

`npm run dev:web` is the MSW mock (no Python server). `--dev` spawns the `apps/web` leaf `npm run dev:api` with `MOLAB_API_PORT` set. `--ui-port` / `MOLAB_WEB_DIR` override the Rsbuild port / web tree.

```
apps/web/src/  →  npm run build:web  →  src/molab/dist/  →  setuptools  →  wheel
```
