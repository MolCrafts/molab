# Molexp Web (`apps/web`)

Single-page application for Molexp that mirrors the Workspace and Workflow split. The UI is registry-driven and renders editors/viewers/inspectors based on semantic object type, file kind, and content type.

## Development

Install once from the **repo root** (npm workspaces):

```bash
npm install
```

Daily UI against a real molexp API is **one command** from the repo root
(after `uv pip install -e ".[dev]"`):

```bash
molexp serve --dev -ws ./lab --port 8000
```

Open the printed **Dev UI** (`:5173`), not the API port. Full three-path
table (HMR / bundled preview / wheel):
[Serve and rebuild the UI](../../docs/en/development/ui-serve.md).

| Root script | Leaf (`cd apps/web`) | Backend | Notes |
|-------------|----------------------|---------|--------|
| `molexp serve --dev` | (spawns leaf `dev:api`) | Real API | Daily checkout path |
| `npm run dev:api` | `npm run dev:api` | Real API (`/api` proxy) | Same UI as `--dev`, API started separately |
| `npm run dev:web` | `npm run dev` | **MSW mock** | Offline showcase; not a real molexp server |

```bash
# Mock showcase (no Python server)
npm run dev:web

# Real backend without molexp serve --dev (API already on :8000)
npm run dev:api
```

Build / check / preview (repo root). `npm run build:web` writes
`src/molexp/dist/`; an editable install does **not** need `uv pip` again.
`-C build-web=true` is the wheel path only (never `build:ui`).

```bash
npm run build:web
npm run typecheck:web
npm run test:web
npm run lint
npm run preview:web
```

## API Client Generation

Auto-generated client from the backend OpenAPI spec (`src/api/generated` — do not hand-edit).

1. Dump the spec (repo root, Python env active):
   ```bash
   python scripts/dump_openapi.py
   ```
2. Regenerate (repo root):
   ```bash
   npm run generate:api
   ```

## Mock layer

`dev` / `dev:web` enables MSW. See [`mocks/README.md`](mocks/README.md) for architecture, seeding, and handler overrides.
