# `.claude/notes/` — passive internal context

This directory holds **passive** internal-agent context for the molexp
repository. Its contents outlive any single feature or spec.

| File | Purpose |
|---|---|
| `notes.md` | Evolving architectural decisions, captured by `/mol:note`. Stable entries are promoted to `CLAUDE.md` and pruned here. |
| `architecture.md` | Project blueprint — modules, public surfaces, layer roles. Built/refreshed by `/mol:map`; consumed by the `librarian` agent at spec time. |
| `integration.md` | Cross-layer coordination contracts (WorkspaceContext, events, provenance); §7.1 is the Workspace Copilot charter. |
| `open-questions.md` | Uncertainties recorded over time; resolved as answers become clear. |
| `ui-serve.md` | UI serve / rebuild command table (`--dev` vs `npm run build:web` vs `-C build-web`). |

## What does *not* belong here

- Active in-flight specs → `.claude/specs/` (alive, ticked off as `/mol:impl` works, deleted on completion)
- Public-user prose → `docs/`
- Skill / agent definitions, hooks, settings → `.claude/` (runtime config)

The split between `.claude/notes/` and `.claude/specs/` is **passive vs
active**: notes are kept; specs are intentionally ephemeral.

## Adding new content

Add subdirectories only when there is real content to seed them:

- `decisions/` — substantial architectural history beyond `notes.md`
- `contracts/` — agent-handoff contracts
- `rubrics/` — review checklists worth encoding
- `debt/` — tracked technical debt
- `handoffs/` — work regularly paused mid-flight

Empty directories are not value.
