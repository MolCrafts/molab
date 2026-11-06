"""FastAPI OpenAPI operationId naming for the Molab API."""

from __future__ import annotations

from fastapi.routing import APIRoute


def molab_operation_id(route: APIRoute) -> str:
    """``create_run`` → ``createRun``; explicit ``operation_id`` wins."""
    explicit = getattr(route, "operation_id", None)
    if explicit:
        return explicit
    name = getattr(route.endpoint, "__name__", "endpoint")
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
