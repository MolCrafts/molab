"""FastAPI OpenAPI operationId naming for the MolExp API."""

from __future__ import annotations

from fastapi.routing import APIRoute


def molexp_operation_id(route: APIRoute) -> str:
    """``create_run`` → ``createRun``; explicit ``operation_id`` wins."""
    explicit = getattr(route, "operation_id", None)
    if explicit:
        return explicit
    name = route.endpoint.__name__
    if name.startswith("_"):
        name = name[1:]
    parts = name.split("_")
    if not parts:
        base = name
    else:
        base = parts[0] + "".join(p.capitalize() for p in parts[1:])
    if "{ws}" in route.path_format:
        return f"{base}Ws"
    return base
