# Product

## Register

product

## Users

Computational scientists and research engineers running FAIR experiments: planning workflows, launching runs, inspecting executions, and curating results into knowledge. They work in focused sessions inside an app shell (not a marketing site), often with many projects and long-running jobs.

## Product Purpose

molab is an agent-assisted scientific-workflow platform. The UI is the operator console for the workspace hierarchy **project → experiment → run → execution**: browse structure, act on lifecycle verbs (run / resume / rerun / cancel), read logs and metrics, and connect results to knowledge. Success looks like a tool that disappears into the experiment — dense when needed, calm when idle, never ornamental.

## Brand Personality

Precise · quiet · confident

Voice is operational and short. Prefer verb + object labels. No marketing cadence. Data and status speak first; chrome stays out of the way.

## Anti-references

- Cluttered lab-software UIs with nested boxes, rainbow icons, and ALL-CAPS section labels on every card
- Generic SaaS “hero metric” dashboards (giant KPI tiles, decorative gradients, identical icon cards)
- Terminal cosplay as the only aesthetic (pure monochrome density without hierarchy)
- Side-stripe accent cards and glassmorphism decoration

## Design Principles

1. **Hierarchy over decoration** — one clear primary surface per view; secondary panels support, never compete
2. **One component vocabulary** — reuse shared workbench controls, connected tabs, quiet dashboard sections, and settings rows; avoid card scaffolding around every entity section
3. **Status is semantic, not colorful chrome** — use status color for state (success / fail / running / pending), with restrained blue for selection and focus
4. **Same shape at every level** — project, experiment, run, and execution overviews share layout, density, and typography
5. **Empty states teach the next action** — never a blank void or a shrug

## Standing Visual Preference

VS Code Compact: light by default with a dark switch, higher information density, borderless icon action buttons, and short operational copy. Dashboard, workspace, and settings share this system. Keep necessary text for navigation, data choices, status, and scientific meaning; action icons retain accessible names and hover titles. See DESIGN.md for the implemented visual system.

## Accessibility & Inclusion

Target WCAG 2.1 AA for text contrast and focus rings. Preserve `prefers-reduced-motion`. Status must not rely on color alone (labels + icons). Tabular numbers for counts and durations.
