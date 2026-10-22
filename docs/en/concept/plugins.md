# Plugins

The plugin layer is how Molab grows beyond the local core without forcing every installation to carry every optional dependency. The guiding rule is simple: `import molab` should still work in a lightweight environment. Heavy integrations are loaded only when the user actually asks for the relevant capability.

## Why Plugins Exist

This boundary protects the core workflow and workspace model. Local authoring, local execution, and workspace inspection should not fail just because a machine does not have cluster tooling or other integration-specific dependencies installed. Plugins make it possible to add those capabilities without turning the base package into a bundle of unrelated operational concerns.

## The Plugins in This Repository

A small registry of optional capabilities ships today. `submit_molq` is the scheduler bridge used when `molab run` needs to submit work to Slurm, PBS, LSF, or another `molq`-backed scheduler. `gh` is a lazy GitHub client. `tensorboard` (installed via `molab[tensorboard]`) parses tfevents into typed Python. In every case the core package stays unaware of those dependencies until the user reaches for the capability.

Beyond this registry, molab also exposes three **third-party** extension channels, each an [entry point](https://packaging.python.org/en/latest/specifications/entry-points/) group (a named slot in a package's metadata that another package can discover at runtime without importing it by name): CLI subcommands (`molab.cli_plugins`), server routes (`molab.server_plugins`), and dynamically-imported UI bundles (`molab.ui_plugins`). A downstream package can extend molab through them without forking it; molab itself registers nothing in these groups. See [Writing a Plugin](../plugins.md) for those channels.

## Scheduler Transport Is Not a Second Runtime

The most important example is `submit_molq`, because it can easily look larger than it really is. The plugin does not define task semantics, replace `Workflow`, or invent a second persistence model. Its job is narrower. It translates CLI scheduling flags into a job submission, launches `python -m molab.cli execute <run_dir>` on the target scheduler, and writes normalized executor metadata back onto the run record.

That design is why local and remote execution remain conceptually aligned. The workflow is still the same workflow. The workspace record is still the same workspace record. Only the transport layer changes.

## Third-Party Extensions Follow the Same Rule

A package attached through `molab.cli_plugins` or `molab.server_plugins` honours the same boundary. It attaches to the command-line app or the web app it is handed, and it stores any durable state it produces in the same workspace hierarchy instead of a private store of its own. What it writes therefore stays inspectable through the same API and UI, and `import molab` stays light because a plugin is imported only when the CLI or server starts and discovers it.

If you need the operational detail behind scheduler submission, continue with [Molq Plugin](../guide/molq.md). If you need the server surface that exposes plugin-backed state to the UI, continue with [Server Lifecycle](../guide/server-lifecycle.md).
