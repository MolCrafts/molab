"""Plugin host: Context, Host, service keys, profile composers.

Import ``molab.harness.host`` — this package is not re-exported from
``molab.harness`` (frozen 22-symbol public surface).
"""

from molab.harness.errors import PluginInjectError
from molab.harness.host.compose import compose_chat, compose_curate, compose_plan, compose_run
from molab.harness.host.context import Context
from molab.harness.host.host import Host
from molab.harness.host.keys import Keys
from molab.harness.host.plugin import Plugin

__all__ = [
    "Context",
    "Host",
    "Keys",
    "Plugin",
    "PluginInjectError",
    "compose_chat",
    "compose_curate",
    "compose_plan",
    "compose_run",
]
