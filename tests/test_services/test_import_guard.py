"""Layer firewall for ``molab.services`` — the application-service layer.

``molab.services`` is the shared backend the CLI and the server both
delegate to (one code path per user-facing operation). Dependency direction:

    cli ──┐
          ├──> services ──> workflow / workspace
 server ──┘

Services may import the domain layers below it (``workflow`` / ``workspace``
/ ``knowledge`` and cross-layer primitives); it MUST NOT import the
application shells that sit above it — ``molab.server``, ``molab.cli``,
``molab.plugins`` — nor ``molab.harness``, which is a *consumer* of molab
and owns its own services under ``molab.harness.services``. The rule holds
statically, anywhere (top level, function bodies, TYPE_CHECKING blocks).

AST source scan: a runtime ``sys.modules`` probe cannot catch an import
hidden inside a function body; the scan catches it regardless of where it
hides.
"""

from __future__ import annotations

import ast
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parents[2] / "src" / "molab" / "services"

# Everything above the services layer — never importable from it.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "molab.harness",
    "molab.server",
    "molab.cli",
    "molab.plugins",
    "molab.sweep",
)


class TestServicesImportGuard:
    def test_services_package_exists(self) -> None:
        assert SERVICES_ROOT.is_dir(), SERVICES_ROOT

    def test_services_forbids_application_shells_statically(self) -> None:
        """No harness / server / cli / plugins imports anywhere in services/."""
        offenders: dict[str, list[str]] = {}
        for prefix in FORBIDDEN_PREFIXES:
            hits = _imports_with_prefix(prefix, SERVICES_ROOT)
            if hits:
                offenders[prefix] = [
                    f"{path.relative_to(SERVICES_ROOT)}:{lineno}: {module}"
                    for path, lineno, module in hits
                ]
        assert not offenders, (
            "molab.services must not import harness or the application "
            "shells (server / cli / plugins).\nOffenders:\n  "
            + "\n  ".join(
                f"[{prefix}] {hit}" for prefix, lines in offenders.items() for hit in lines
            )
        )

    def test_static_scan_detects_planted_violations(self, tmp_path: Path) -> None:
        """Negative test: the AST scan must catch freshly-planted bad imports."""
        fake = tmp_path / "tainted.py"
        fake.write_text(
            "def sneaky():\n"
            "    from molab.server.app import create_app\n"
            "    import molab.cli\n"
            "    return create_app, molab\n"
        )
        server_hits = _imports_with_prefix("molab.server", tmp_path)
        cli_hits = _imports_with_prefix("molab.cli", tmp_path)
        assert any(p == fake and m == "molab.server.app" for p, _, m in server_hits)
        assert any(p == fake for p, _, _ in cli_hits)


def _imports_with_prefix(prefix: str, root: Path) -> list[tuple[Path, int, str]]:
    """Return ``(path, lineno, module)`` for every import matching ``prefix``."""
    hits: list[tuple[Path, int, str]] = []
    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == prefix or alias.name.startswith(prefix + "."):
                        hits.append((py, node.lineno, alias.name))
                        break
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module and (module == prefix or module.startswith(prefix + ".")):
                    hits.append((py, node.lineno, module))
    return hits
