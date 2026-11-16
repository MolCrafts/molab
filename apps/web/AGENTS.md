# AGENTS.md

You are an expert in JavaScript, Rsbuild, and web application development. You write maintainable, performant, and accessible code.

## Commands

**From repo root** (molvis-style `verb:package`):

| Script | What |
|--------|------|
| `molab serve --dev` | Daily checkout: API + Dev UI (`:5173`). Do not `uv pip` to pick up UI edits. |
| `npm run dev:web` | Web UI with **MSW mock** + seeded showcase (offline; not a real API) |
| `npm run dev:api` | Web UI against a real API (`/api` proxy; start API separately or use `molab serve --dev`) |
| `npm run build:web` | Production build → `src/molab/dist/` (editable: no reinstall; wheel: `-C build-web=true`) |
| `npm run build:molrs` | Rebuild sibling molrs WASM into `molrs-wasm/.x86_64` (x86_64 toolchain). Dev aliases this; CI/publish use npm `@molcrafts/molrs` |
| `npm run build:rsdoctor` | Production build with Rsdoctor brief JSON (`RSDOCTOR=true`) |
| `npm run preview:web` | Preview the production build |
| `npm run typecheck:web` / `test:web` / `lint` / `lint:fix` / `format` | Checks |
| `npm run generate:api` | Regenerate OpenAPI client |

**From `apps/web/`** (leaf verbs):

`dev` (mock) · `dev:api` (real proxy) · `build` · `build:molrs` · `build:rsdoctor` · `preview` · `typecheck` · `test` · `test:watch` · `lint` · `lint:fix` · `format` · `generate:api`

## Docs

- Rsbuild: https://rsbuild.rs/llms.txt
- Rspack: https://rspack.rs/llms.txt
