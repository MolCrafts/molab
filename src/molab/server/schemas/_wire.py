"""Shared OpenAPI wire-model base for the Molab API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Pydantic base for JSON request/response bodies exposed in OpenAPI.

    Python fields stay snake_case; serialized JSON uses camelCase.
    ``populate_by_name=True`` accepts either spelling on input.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
