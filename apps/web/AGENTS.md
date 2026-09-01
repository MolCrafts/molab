# AGENTS.md

You are an expert in JavaScript, Rsbuild, and web application development. You write maintainable, performant, and accessible code.

## Commands

**From repo root** (molvis-style `verb:package`):

| Script | What |
|--------|------|
| `molexp serve --dev` | Daily checkout: API + Dev UI (`:5173`). Do not `uv pip` to pick up UI edits. |
| `npm run dev:web` | Web UI with **MSW mock** + seeded showcase (offline; not a real API) |
| `npm run dev:api` | Web UI against a real API (`/api` proxy; start API separately or use `molexp serve --dev`) |
| `npm run build:web` | Production build → `src/molexp/dist/` (editable: no reinstall; wheel: `-C build-web=true`) |
| `npm run preview:web` | Preview the production build |
| `npm run typecheck:web` / `test:web` / `lint` / `lint:fix` / `format` | Checks |
| `npm run generate:api` | Regenerate OpenAPI client |

**From `apps/web/`** (leaf verbs):

`dev` (mock) · `dev:api` (real proxy) · `build` · `preview` · `typecheck` · `test` · `test:watch` · `lint` · `lint:fix` · `format` · `generate:api`

## Docs

- Rsbuild: https://rsbuild.rs/llms.txt
- Rspack: https://rspack.rs/llms.txt
