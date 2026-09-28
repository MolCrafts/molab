# Architecture

Architecture docs describe layer boundaries that must remain true as the code
evolves.

molab is layered as a small dependency DAG (directed acyclic graph — every
arrow points one way, and no chain of arrows leads back to where it started):
`workspace` is the storage foundation, `workflow` and `knowledge` sit on top of
it, and the `cli` / `server` application shells sit on top of everything
through the `services` layer. Third-party packages extend the shells through
the `molab.cli_plugins`, `molab.server_plugins` and `molab.ui_plugins` entry
points (see [Writing a Plugin](../plugins.md)); molab itself registers none.

- [Workflow Layer](workflow-layer.md) — `molab.workflow` as the single workflow
  abstraction; the engine is fully self-owned under `_engine/` (no `pydantic_graph` dependency). Also covers
  the boundary between workspace storage primitives and the workflow engine
  that consumes them.
