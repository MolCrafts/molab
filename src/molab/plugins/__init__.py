"""In-tree adapters and the three third-party plugin channels.

Plugin naming convention: ``{category}_{implementation}`` or the product name
when the plugin *is* that product's molab adapter:

- ``molpy`` — dataset preview through molpy's per-format readers
- ``molvis`` — headless snapshots via molvis
- ``submit_molq`` — job submission via molq schedulers

Third-party packages attach through the ``molab.cli_plugins`` /
``molab.server_plugins`` / ``molab.ui_plugins`` entry-point groups.
"""

from __future__ import annotations

from molab.plugins.cli import (
    CLI_PLUGIN_API_VERSION,
    CliPlugin,
    discover_cli_plugins,
)
from molab.plugins.server import (
    SERVER_PLUGIN_API_VERSION,
    ServerPlugin,
    discover_server_plugins,
    signal_shutdown_server_plugins,
)
from molab.plugins.ui import discover_ui_plugin_dirs

__all__ = [
    "CLI_PLUGIN_API_VERSION",
    "SERVER_PLUGIN_API_VERSION",
    "CliPlugin",
    "ServerPlugin",
    "discover_cli_plugins",
    "discover_server_plugins",
    "discover_ui_plugin_dirs",
    "signal_shutdown_server_plugins",
]
