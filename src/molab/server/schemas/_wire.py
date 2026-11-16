"""Shared OpenAPI wire-model base for the Molab API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, WithJsonSchema
from pydantic.alias_generators import to_camel

from molab.knowledge.concepts import _PRODUCTS, HARVEST_TARGETS


def _key_of(table: Mapping[str, object]) -> Callable[[str], str]:
    """A validator that accepts only a key of *table* (a 422 names the keys)."""

    def check(name: str) -> str:
        if name not in table:
            raise ValueError(f"{name!r} is not one of {', '.join(table)}")
        return name

    return check


#: A knowledge class name: the keys of the knowledge class table, listed in OpenAPI.
KnowledgeClassName = Annotated[
    str,
    AfterValidator(_key_of(_PRODUCTS)),
    WithJsonSchema({"type": "string", "enum": list(_PRODUCTS)}),
]

#: A class a run can be harvested into: the keys of ``HARVEST_TARGETS``.
HarvestClassName = Annotated[
    str,
    AfterValidator(_key_of(HARVEST_TARGETS)),
    WithJsonSchema({"type": "string", "enum": list(HARVEST_TARGETS)}),
]


class ApiModel(BaseModel):
    """Pydantic base for JSON request/response bodies exposed in OpenAPI.

    Python fields stay snake_case; serialized JSON uses camelCase.
    ``populate_by_name=True`` accepts either spelling on input.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
