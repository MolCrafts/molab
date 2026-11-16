"""Explicit, private configuration for the proxy and fixed-UID user service."""

from __future__ import annotations

import hmac
import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator

from .models import SharingModel


class ProxySettings(SharingModel):
    issuer: str = Field(min_length=1, max_length=500)
    proxy_key: SecretStr = Field(min_length=32)
    public_origin: AnyHttpUrl

    @field_validator("public_origin")
    @classmethod
    def validate_origin(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment or value.path != "/":
            raise ValueError("public_origin must be an origin without credentials or a path")
        if value.scheme != "https" and value.host not in {"localhost", "127.0.0.1", "[::1]"}:
            raise ValueError("public_origin requires HTTPS outside loopback development")
        return value

    def accepts(self, key: str | None) -> bool:
        return key is not None and hmac.compare_digest(
            key.encode(), self.proxy_key.get_secret_value().encode()
        )


class GatewaySettings(ProxySettings):
    state_dir: Path
    # An administrator asserts the deployment contract; mount heuristics alone
    # cannot prove correct SQLite locking or local persistence.
    local_state_confirmed: bool


class AssetStorageSettings(SharingModel):
    # The same administrator-provisioned shared mount on every user service.
    root: Path
    backend: Literal["auto", "posix", "nfsv4", "group"] = "auto"
    nfsv4_domain: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9.-]+$")
    group_id: int | None = Field(default=None, ge=1)
    group_exposure_confirmed: bool = False
    max_file_bytes: int = Field(default=1024**4, ge=1)

    @model_validator(mode="after")
    def validate_storage(self) -> AssetStorageSettings:
        if not self.root.is_absolute():
            raise ValueError("asset publication root must be an absolute path")
        if self.backend == "group" and (self.group_id is None or not self.group_exposure_confirmed):
            raise ValueError(
                "group sharing requires a configured GID and explicit group exposure consent"
            )
        return self


class WorkerSettings(ProxySettings):
    principal_id: str
    subject: str = Field(min_length=1)
    uid: int = Field(ge=1)
    cluster_id: str = Field(min_length=1)
    gateway_url: AnyHttpUrl
    source_token: SecretStr = Field(min_length=32)
    asset_storage: AssetStorageSettings | None = None

    @field_validator("gateway_url")
    @classmethod
    def validate_gateway_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        return cls.validate_origin(value)

    def assert_uid(self) -> None:
        if not hasattr(os, "getuid") or os.getuid() != self.uid or os.geteuid() != self.uid:
            raise ValueError("managed workspace service must run as its configured non-root UID")


def read_private_config(path: Path) -> str:
    """Read only a regular, owner-only config; never follow a supplied symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError(
                "sharing config must be a regular file owned by this UID with mode 0600"
            )
        return handle.read()
