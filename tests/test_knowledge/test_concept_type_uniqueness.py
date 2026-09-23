"""Every concept ``type`` string is claimed by exactly one class in ``src/``.

``register_concept_type`` raises on a collision, so a second class claiming an
already-registered type is an **import-time hard failure**: ``molab`` stops
importing at all and every test, the CLI and the server go down with it. That
failure mode is easy to introduce while moving Concept classes between layers —
a re-export shim that accidentally *re-declares* ``@concept_type(...)`` instead
of re-exporting the original class object does exactly this.

A type string is claimed through one of two registries — the knowledge-owned
concept-type registry (``@concept_type(...)``) or the workspace-owned
``meta.json`` type table (``@register_folder_type(...)``, for a Folder whose
identity file is ``meta.json`` alone). Both go through the same one-claim-per-
storage-family rule, so this one scan reads both decorators rather than
proliferating a second scanner.

An AST scan catches a collision as a readable assertion naming both offenders,
rather than as a collection error with no context, and reports every duplicate
at once instead of only the first one Python happens to hit.

Every decorator in the tree spells its type through a module-level constant
(``@concept_type(NOTE_KIND)``), never a bare literal, so the scanner resolves
module-level string constants — following in-module aliases and ``from .mod
import NAME`` edges — before comparing. A name it cannot resolve is recorded
qualified by its module, so an unresolved constant can never *fake* a collision.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "molab"

#: The decorators that claim a ``type`` string for a storage family.
_TYPE_CLAIM_DECORATORS = frozenset({"concept_type", "register_folder_type"})

#: The subset claiming through the workspace-owned ``meta.json`` type table.
_FOLDER_TYPE_CLAIM_DECORATORS = frozenset({"register_folder_type"})


def _module_name(py: Path) -> str:
    """Dotted ``molab.…`` module name for *py*."""
    rel = py.relative_to(SRC_ROOT.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _parsed() -> dict[str, ast.Module]:
    """Every ``src/molab`` module, parsed, keyed by dotted module name."""
    trees: dict[str, ast.Module] = {}
    for py in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        trees[_module_name(py)] = ast.parse(py.read_text(encoding="utf-8"))
    return trees


def _string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings."""
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            out[target.id] = node.value.value
    return out


def _local_aliases(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = OTHER`` bindings (one alias hop)."""
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Name):
            out[target.id] = node.value.id
    return out


def _import_origins(module: str, tree: ast.Module) -> dict[str, str]:
    """Map each ``from X import NAME`` binding to its defining module."""
    out: dict[str, str] = {}
    package = module.rsplit(".", 1)[0] if "." in module else module
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:  # relative import — resolve against the owning package
            base = package
            for _ in range(node.level - 1):
                base = base.rsplit(".", 1)[0]
            origin = f"{base}.{node.module}" if node.module else base
        elif node.module:
            origin = node.module
        else:
            continue
        for alias in node.names:
            out[alias.asname or alias.name] = origin
    return out


def _resolve(name: str, module: str, trees: dict[str, ast.Module]) -> str | None:
    """Resolve *name* in *module* to a string literal, or ``None``."""
    seen: set[tuple[str, str]] = set()
    while (module, name) not in seen:
        seen.add((module, name))
        tree = trees.get(module)
        if tree is None:
            return None
        constants = _string_constants(tree)
        if name in constants:
            return constants[name]
        aliases = _local_aliases(tree)
        if name in aliases:
            name = aliases[name]
            continue
        origins = _import_origins(module, tree)
        if name in origins:
            module = origins[name]
            continue
        return None
    return None


def _claims(decorators: frozenset[str] = _TYPE_CLAIM_DECORATORS) -> dict[str, list[str]]:
    """Map each claimed type string to the ``module::Class`` sites claiming it.

    Both claiming decorators are read by default: ``@concept_type(...)`` (the
    knowledge concept-type registry) and ``@register_folder_type(...)`` (the
    workspace ``meta.json`` type table). Pass *decorators* to read one of them.
    """
    trees = _parsed()
    by_type: dict[str, list[str]] = defaultdict(list)
    for module, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or not deco.args:
                    continue
                func = deco.func
                fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if fname not in decorators:
                    continue
                arg = deco.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    type_str: str | None = arg.value
                elif isinstance(arg, ast.Name):
                    type_str = _resolve(arg.id, module, trees)
                    # Qualify an unresolved name by module so it cannot collide.
                    if type_str is None:
                        type_str = f"<unresolved {module}.{arg.id}>"
                else:
                    type_str = f"<dynamic {module}.{node.name}>"
                by_type[type_str].append(f"{module}::{node.name}")
    return by_type


#: The agent kinds are claimed through the workspace ``meta.json`` type table,
#: by the layer that owns their Folder classes. One claim each, no duplicate.
_FOLDER_TYPE_REGISTRY_CLAIMS = {
    "agent.agent": "molab.harness.agent.folders::Agent",
    "agent.session": "molab.harness.agent.folders::AgentSession",
}


def test_each_concept_type_is_claimed_once_per_family() -> None:
    duplicates = {t: sites for t, sites in _claims().items() if len(sites) > 1}
    assert duplicates == {}, (
        f"a concept type claimed twice within one family shadows a class silently; "
        f"duplicates: {duplicates}"
    )


def test_folder_type_claims_come_from_their_owning_classes() -> None:
    """``@register_folder_type`` claims are read by the same scan as ``@concept_type``."""
    claimed = _claims(_FOLDER_TYPE_CLAIM_DECORATORS)
    for type_str, site in _FOLDER_TYPE_REGISTRY_CLAIMS.items():
        assert claimed.get(type_str) == [site], (
            f"{type_str} must be claimed exactly once, by {site}; got {claimed.get(type_str)}"
        )


def test_scan_resolves_the_known_concept_types() -> None:
    # Negative control: a scanner that resolved nothing would make the
    # uniqueness assertion vacuously true.
    claimed = _claims()
    for expected in (
        "note.note",
        "reference.reference",
        "knowledge.item",
        "workspace.run",
        "agent.agent",
        "agent.session",
    ):
        assert expected in claimed, f"{expected} not resolved; claimed={sorted(claimed)}"
