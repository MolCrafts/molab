"""Read-only permissions on fresh publication copies, never workspace trees."""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
from pathlib import Path

from .settings import AssetStorageSettings
from .store import SharingError


class FilesystemPermissionBackend:
    """Select a filesystem-supported ACL, or an explicitly configured group.

    Instances belong to one immutable publication directory. Group mode has a
    wider native audience and is therefore never an automatic fallback.
    """

    def __init__(self, settings: AssetStorageSettings, directory: Path) -> None:
        self.settings = settings
        self.kind = settings.backend
        if self.kind == "auto":
            self.kind = "nfsv4" if self._supports("nfs4_getfacl", directory) else "posix"
        if self.kind == "group":
            if self._supports("nfs4_getfacl", directory):
                raise SharingError(422, "Use the NFSv4 ACL backend on this filesystem")
            if settings.group_id not in os.getgroups() and settings.group_id != os.getgid():
                raise SharingError(
                    422, "The owner service is not a member of the configured sharing group"
                )
            return
        required = (
            ("getfacl", "setfacl") if self.kind == "posix" else ("nfs4_getfacl", "nfs4_setfacl")
        )
        if any(shutil.which(tool) is None for tool in required) or not self._supports(
            required[0], directory
        ):
            raise SharingError(
                422, f"The publication filesystem does not support the {self.kind} ACL backend"
            )

    @staticmethod
    def _supports(tool: str, path: Path) -> bool:
        if shutil.which(tool) is None:
            return False
        try:
            result = subprocess.run([tool, str(path)], capture_output=True, timeout=10, check=False)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _run(*args: str) -> str:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SharingError(422, "The filesystem permission tool is unavailable") from exc
        if result.returncode:
            raise SharingError(422, "The filesystem rejected the requested read-only permission")
        return result.stdout

    def _set_nfsv4(self, path: Path, *, directory: bool, principal: str | None = None) -> None:
        owner = "rwaDxtTnNcCy" if directory else "rwatTnNcCy"
        permissions = "xntcy" if directory else "rntcy"
        entries = f"A::OWNER@:{owner}"
        if principal is not None:
            entries += f",A::{principal}:{permissions}"
        self._run("nfs4_setfacl", "-s", entries, str(path))
        matched: set[str] = set()
        for line in self._run("nfs4_getfacl", str(path)).splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split(":")
            if len(fields) != 4 or fields[0] != "A":
                raise SharingError(422, "NFSv4 server returned an unsupported ACL representation")
            _, flags, who, allowed = fields
            if flags or who not in {"OWNER@", principal}:
                if allowed:
                    raise SharingError(422, "NFSv4 server retained an unexpected filesystem grant")
            elif who == principal:
                if set(allowed) != set(permissions):
                    raise SharingError(
                        422, "NFSv4 server did not preserve the requested read-only grant"
                    )
            elif who == "OWNER@" and set(allowed) != set(owner):
                raise SharingError(
                    422, "NFSv4 server did not preserve the owner's publication access"
                )
            matched.add(who)
        if "OWNER@" not in matched or (principal is not None and principal not in matched):
            raise SharingError(422, "NFSv4 server did not install the requested ACL")

    def prepare(self, directory: Path) -> None:
        """Remove inherited readers before any private bytes enter the copy."""
        if self.kind == "nfsv4":
            self._set_nfsv4(directory, directory=True)
        else:
            if not self._supports("getfacl", directory):
                raise SharingError(422, "Publication storage requires POSIX ACL inspection tools")
            self._run("setfacl", "-b", "-k", str(directory))
            directory.chmod(0o700)

    def grant(self, directory: Path, payload: Path, recipient_uid: int) -> None:
        if recipient_uid == os.getuid():
            raise SharingError(422, "Asset recipients must use a different Linux UID")
        if self.kind == "posix":
            # The parent was sanitized before the copy; ensure the payload has
            # no named access entries before granting exactly one reader.
            self._run("setfacl", "-b", str(payload))
            self._run(
                "setfacl", "-m", f"u::r--,u:{recipient_uid}:r--,g::---,m::r--,o::---", str(payload)
            )
            self._run(
                "setfacl",
                "-m",
                f"u::rwx,u:{recipient_uid}:--x,g::---,m::--x,o::---",
                str(directory),
            )
        elif self.kind == "nfsv4":
            try:
                username = pwd.getpwuid(recipient_uid).pw_name
            except KeyError as exc:
                raise SharingError(
                    422, "Recipient UID cannot be resolved through the cluster identity service"
                ) from exc
            if not self.settings.nfsv4_domain:
                raise SharingError(
                    422, "NFSv4 sharing requires the cluster's configured ACL identity domain"
                )
            if any(char in username for char in ":,@\n\r"):
                raise SharingError(
                    422, "Recipient name cannot be represented by the NFSv4 ACL backend"
                )
            principal = f"{username}@{self.settings.nfsv4_domain}"
            # Replace, rather than append to, inherited NFSv4 ACLs.
            self._set_nfsv4(payload, directory=False, principal=principal)
            self._set_nfsv4(directory, directory=True, principal=principal)
        else:
            assert self.settings.group_id is not None
            try:
                user = pwd.getpwuid(recipient_uid)
                grp.getgrgid(self.settings.group_id)
            except KeyError as exc:
                raise SharingError(
                    422, "Configured sharing group or recipient UID is unavailable"
                ) from exc
            if self.settings.group_id not in os.getgrouplist(user.pw_name, user.pw_gid):
                raise SharingError(422, "Recipient is not a member of the configured sharing group")
            # prepare() removed named/default ACLs before any bytes were copied.
            self._run("setfacl", "-b", str(payload))
            os.chown(directory, -1, self.settings.group_id)
            os.chown(payload, -1, self.settings.group_id)
            payload.chmod(0o440)
            directory.chmod(0o2710)
