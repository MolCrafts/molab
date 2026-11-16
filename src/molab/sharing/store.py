"""Transactional control-plane state, never stored inside a user workspace."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path

from molab.fs.profile import FsKind, detect_fs_profile
from molab.ids import compute_definition_hash, generate_uuid7

from .models import (
    AssetShare,
    AssetTransfer,
    BeginPublication,
    PrepareAssetShare,
    Principal,
    PublicationBatch,
)

audit_request_id: ContextVar[str | None] = ContextVar("sharing_audit_request_id", default=None)

_SCHEMA = """
CREATE TABLE principals (
 id TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
 display_name TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0,
 UNIQUE(issuer, subject)
);
CREATE TABLE principal_bindings (
 principal_id TEXT NOT NULL REFERENCES principals(id), cluster_id TEXT NOT NULL,
 uid INTEGER NOT NULL CHECK(uid > 0), PRIMARY KEY(cluster_id, uid),
 UNIQUE(principal_id, cluster_id)
);
CREATE TABLE sources (
 id TEXT PRIMARY KEY, principal_id TEXT NOT NULL REFERENCES principals(id),
 cluster_id TEXT NOT NULL, uid INTEGER NOT NULL,
 token_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, last_seen_at TEXT
);
CREATE TABLE shared_projects (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
 workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,
 owner_id TEXT NOT NULL REFERENCES principals(id),
 current_version TEXT, active INTEGER NOT NULL DEFAULT 0, generation INTEGER NOT NULL DEFAULT 0,
 UNIQUE(source_id, workspace_id, project_id)
);
CREATE TABLE grants (
 project_id TEXT NOT NULL REFERENCES shared_projects(id),
 principal_id TEXT NOT NULL REFERENCES principals(id),
 role TEXT NOT NULL CHECK(role = 'viewer'), created_at TEXT NOT NULL, revoked_at TEXT,
 PRIMARY KEY(project_id, principal_id)
);
CREATE TABLE invitations (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES shared_projects(id),
 recipient_id TEXT NOT NULL REFERENCES principals(id), created_by TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','accepted','declined','revoked')),
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE UNIQUE INDEX pending_invitation ON invitations(project_id, recipient_id)
 WHERE status = 'pending';
CREATE TABLE publications (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES shared_projects(id),
 base_version TEXT, base_generation INTEGER NOT NULL, project_json TEXT NOT NULL,
 created_at TEXT NOT NULL, committed_at TEXT
);
CREATE TABLE publication_batches (
 version_id TEXT NOT NULL REFERENCES publications(id), batch_id INTEGER NOT NULL,
 digest TEXT NOT NULL, PRIMARY KEY(version_id, batch_id)
);
CREATE TABLE publication_objects (
 version_id TEXT NOT NULL REFERENCES publications(id), kind TEXT NOT NULL,
 entity_id TEXT NOT NULL, parent_id TEXT NOT NULL, body TEXT NOT NULL,
 PRIMARY KEY(version_id, kind, entity_id, parent_id)
);
CREATE TABLE audit_events (
 id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, action TEXT NOT NULL,
 object_id TEXT NOT NULL, occurred_at TEXT NOT NULL, request_id TEXT NOT NULL,
 result TEXT NOT NULL CHECK(result = 'success')
);
PRAGMA user_version = 1;
"""

_ASSET_SCHEMA = """
CREATE TABLE asset_shares (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES shared_projects(id),
 source_id TEXT NOT NULL REFERENCES sources(id), asset_id TEXT NOT NULL,
 recipient_id TEXT NOT NULL REFERENCES principals(id), title TEXT NOT NULL,
 digest TEXT NOT NULL, size INTEGER NOT NULL CHECK(size >= 0),
 owner_uid INTEGER NOT NULL, recipient_uid INTEGER NOT NULL, cluster_id TEXT NOT NULL,
 storage_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('preparing','active','revoking','revoked')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX asset_shares_project ON asset_shares(project_id, recipient_id);
CREATE INDEX asset_shares_cleanup ON asset_shares(source_id, state);
PRAGMA user_version = 2;
"""


class SharingError(Exception):
    """An expected sharing failure with an HTTP-compatible status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class SharingStore:
    def __init__(self, state_dir: Path, *, local_state_confirmed: bool) -> None:
        if not local_state_confirmed:
            raise ValueError("sharing state requires administrator-confirmed persistent local disk")
        if detect_fs_profile(state_dir).kind != FsKind.LOCAL_FAST:
            raise ValueError("sharing database must not reside on network or remote storage")
        if state_dir.is_symlink():
            raise ValueError("sharing state directory must not be a symlink")
        state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = state_dir.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("sharing state directory must belong to this UID with mode 0700")
        state_dir = state_dir.resolve()
        for parent in state_dir.parents:
            ancestor = parent.stat()
            if ancestor.st_uid not in {0, os.getuid()} or (
                ancestor.st_mode & 0o022 and not ancestor.st_mode & stat.S_ISVTX
            ):
                raise ValueError(
                    "sharing state ancestors must not allow another user to replace the directory"
                )
        self.path = state_dir / "sharing.sqlite3"
        # Create with restrictive permissions before SQLite touches the file.
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("sharing database must belong to this UID with mode 0600")
        finally:
            os.close(fd)
        with self._transaction(write=True) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                # executescript commits implicitly; initialization is a local
                # operator action, before the application starts serving.
                conn.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA)
                version = 1
            if version == 1:
                # Keep the migration in the same startup transaction.
                for statement in _ASSET_SCHEMA.split(";"):
                    if statement.strip():
                        conn.execute(statement)
            elif version != 2:
                raise ValueError(f"unsupported sharing database version: {version}")

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Generator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _audit(conn: sqlite3.Connection, actor: str, action: str, target: str) -> None:
        conn.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, 'success')",
            (
                generate_uuid7(),
                actor,
                action,
                target,
                datetime.now(UTC).isoformat(),
                audit_request_id.get() or generate_uuid7(),
            ),
        )

    @staticmethod
    def _actor(conn: sqlite3.Connection, principal_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM principals WHERE id = ? AND disabled = 0", (principal_id,)
        ).fetchone()
        if row is None:
            raise SharingError(401, "Authentication required")
        return row

    def provision_principal(self, issuer: str, subject: str, display_name: str) -> Principal:
        with self._transaction(write=True) as conn:
            row = conn.execute(
                "SELECT * FROM principals WHERE issuer = ? AND subject = ?", (issuer, subject)
            ).fetchone()
            if row is None:
                principal_id = generate_uuid7()
                conn.execute(
                    "INSERT INTO principals VALUES (?, ?, ?, ?, 0)",
                    (principal_id, issuer, subject, display_name),
                )
                self._audit(conn, "administrator", "principal.provisioned", principal_id)
            else:
                principal_id = row["id"]
                if row["display_name"] != display_name:
                    conn.execute(
                        "UPDATE principals SET display_name = ? WHERE id = ?",
                        (display_name, principal_id),
                    )
                    self._audit(conn, "administrator", "principal.renamed", principal_id)
            result = dict(
                conn.execute("SELECT * FROM principals WHERE id = ?", (principal_id,)).fetchone()
            )
            result["disabled"] = bool(result["disabled"])
            return Principal.model_validate(result)

    def principal(self, issuer: str, subject: str) -> Principal:
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM principals WHERE issuer = ? AND subject = ? AND disabled = 0",
                (issuer, subject),
            ).fetchone()
            if row is None:
                raise SharingError(401, "Identity is not provisioned or is disabled")
            result = dict(row)
            result["disabled"] = bool(result["disabled"])
            return Principal.model_validate(result)

    def disable_principal(self, principal_id: str) -> None:
        with self._transaction(write=True) as conn:
            conn.execute("UPDATE principals SET disabled = 1 WHERE id = ?", (principal_id,))
            conn.execute(
                "UPDATE asset_shares SET state = 'revoking', updated_at = ? "
                "WHERE state IN ('preparing', 'active') AND (recipient_id = ? OR "
                "source_id IN (SELECT id FROM sources WHERE principal_id = ?))",
                (datetime.now(UTC).isoformat(), principal_id, principal_id),
            )
            self._audit(conn, "administrator", "principal.disabled", principal_id)

    def provision_source(self, principal_id: str, cluster_id: str, uid: int) -> tuple[str, str]:
        if uid <= 0:
            raise ValueError("a source requires a non-root UID")
        source_id, token = generate_uuid7(), secrets.token_urlsafe(32)
        with self._transaction(write=True) as conn:
            self._actor(conn, principal_id)
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO principal_bindings VALUES (?, ?, ?)",
                    (principal_id, cluster_id, uid),
                )
                binding = conn.execute(
                    "SELECT principal_id, uid FROM principal_bindings WHERE cluster_id = ? AND uid = ?",
                    (cluster_id, uid),
                ).fetchone()
                if binding is None or binding["principal_id"] != principal_id:
                    raise SharingError(409, "Linux identity is already bound or binding changed")
                conn.execute(
                    "INSERT INTO sources VALUES (?, ?, ?, ?, ?, 0, NULL)",
                    (
                        source_id,
                        principal_id,
                        cluster_id,
                        uid,
                        hashlib.sha256(token.encode()).hexdigest(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise SharingError(409, "Linux identity binding conflicts") from exc
            self._audit(conn, "administrator", "source.provisioned", source_id)
        return source_id, f"{source_id}.{token}"

    def disable_source(self, source_id: str) -> None:
        with self._transaction(write=True) as conn:
            conn.execute("UPDATE sources SET disabled = 1 WHERE id = ?", (source_id,))
            conn.execute(
                "UPDATE asset_shares SET state = 'revoking', updated_at = ? "
                "WHERE source_id = ? AND state IN ('preparing', 'active')",
                (datetime.now(UTC).isoformat(), source_id),
            )
            self._audit(conn, "administrator", "source.disabled", source_id)

    @staticmethod
    def _source(
        conn: sqlite3.Connection, credential: str, *, cleanup_only: bool = False
    ) -> sqlite3.Row:
        source_id, separator, token = credential.partition(".")
        row = conn.execute(
            "SELECT s.* FROM sources s JOIN principals p ON p.id = s.principal_id "
            "WHERE s.id = ? AND (? OR (s.disabled = 0 AND p.disabled = 0))",
            (source_id, cleanup_only),
        ).fetchone()
        supplied = hashlib.sha256(token.encode()).hexdigest()
        expected = row["token_hash"] if row else "0" * 64
        if not separator or not secrets.compare_digest(supplied, expected) or row is None:
            raise SharingError(401, "Invalid source credential")
        return row

    def source_identity(self, credential: str) -> dict[str, object]:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential)
            conn.execute(
                "UPDATE sources SET last_seen_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), source["id"]),
            )
            return {key: source[key] for key in ("id", "principal_id", "cluster_id", "uid")}

    def source_project(
        self, credential: str, workspace_id: str, project_id: str
    ) -> dict[str, object]:
        with self._transaction() as conn:
            source = self._source(conn, credential)
            row = conn.execute(
                "SELECT id, current_version, active FROM shared_projects WHERE source_id = ? AND workspace_id = ? AND project_id = ?",
                (source["id"], workspace_id, project_id),
            ).fetchone()
            return dict(row) if row else {"id": None, "current_version": None, "active": False}

    def begin_publication(self, credential: str, body: BeginPublication) -> dict[str, object]:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential)
            expired = (
                "SELECT v.id FROM publications v JOIN shared_projects p ON p.id = v.project_id "
                "WHERE p.source_id = ? AND v.committed_at IS NULL AND v.created_at < ?"
            )
            args = (source["id"], (datetime.now(UTC) - timedelta(days=1)).isoformat())
            conn.execute(
                "DELETE FROM publication_objects WHERE version_id IN (" + expired + ")", args
            )
            conn.execute(
                "DELETE FROM publication_batches WHERE version_id IN (" + expired + ")", args
            )
            conn.execute("DELETE FROM publications WHERE id IN (" + expired + ")", args)
            pending = conn.execute(
                "SELECT COUNT(*) FROM publications v JOIN shared_projects p ON p.id = v.project_id "
                "WHERE p.source_id = ? AND v.committed_at IS NULL",
                (source["id"],),
            ).fetchone()[0]
            if pending >= 32:
                raise SharingError(429, "Source has too many pending publications")
            project = conn.execute(
                "SELECT * FROM shared_projects WHERE source_id = ? AND workspace_id = ? AND project_id = ?",
                (source["id"], body.workspace_id, body.project.id),
            ).fetchone()
            if project is None:
                if body.base_version is not None:
                    raise SharingError(409, "Publication base version changed")
                project_id = generate_uuid7()
                conn.execute(
                    "INSERT INTO shared_projects(id, source_id, workspace_id, project_id, owner_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        project_id,
                        source["id"],
                        body.workspace_id,
                        body.project.id,
                        source["principal_id"],
                    ),
                )
                current_version, generation = None, 0
            else:
                project_id, current_version = project["id"], project["current_version"]
                generation = project["generation"]
                if current_version is not None and not project["active"] and not body.activate:
                    raise SharingError(409, "Publication was stopped; owner confirmation required")
            if current_version != body.base_version:
                raise SharingError(409, "Publication base version changed")
            pending_project = conn.execute(
                "SELECT COUNT(*) FROM publications WHERE project_id = ? AND committed_at IS NULL",
                (project_id,),
            ).fetchone()[0]
            if pending_project >= 4:
                raise SharingError(429, "Project has too many pending publications")
            version_id = generate_uuid7()
            conn.execute(
                "INSERT INTO publications VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (
                    version_id,
                    project_id,
                    body.base_version,
                    generation,
                    body.project.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._audit(conn, source["principal_id"], "publication.started", version_id)
            return {"project_id": project_id, "version_id": version_id}

    def _draft(self, conn: sqlite3.Connection, credential: str, version_id: str) -> sqlite3.Row:
        source = self._source(conn, credential)
        row = conn.execute(
            "SELECT v.*, p.source_id, p.current_version, p.generation AS current_generation FROM publications v "
            "JOIN shared_projects p ON p.id = v.project_id WHERE v.id = ? AND p.source_id = ?",
            (version_id, source["id"]),
        ).fetchone()
        if row is None:
            raise SharingError(404, "Publication not found")
        if row["committed_at"] is not None:
            raise SharingError(409, "Publication is already committed")
        if datetime.fromisoformat(row["created_at"]) < datetime.now(UTC) - timedelta(days=1):
            raise SharingError(410, "Publication expired")
        return row

    def add_batch(
        self, credential: str, version_id: str, batch_id: int, body: PublicationBatch
    ) -> None:
        digest = compute_definition_hash(body.model_dump(mode="json"))
        with self._transaction(write=True) as conn:
            self._draft(conn, credential, version_id)
            existing = conn.execute(
                "SELECT digest FROM publication_batches WHERE version_id = ? AND batch_id = ?",
                (version_id, batch_id),
            ).fetchone()
            if existing:
                if existing["digest"] != digest:
                    raise SharingError(409, "Batch content changed")
                return
            count = conn.execute(
                "SELECT COUNT(*) FROM publication_objects WHERE version_id = ?", (version_id,)
            ).fetchone()[0]
            if count + len(body.experiments) + len(body.runs) > 20000:
                raise SharingError(413, "Publication exceeds 20000 objects")
            size = conn.execute(
                "SELECT COALESCE(SUM(length(CAST(body AS BLOB))), 0) FROM publication_objects WHERE version_id = ?",
                (version_id,),
            ).fetchone()[0]
            added = sum(
                len(item.model_dump_json().encode()) for item in [*body.experiments, *body.runs]
            )
            if size + added > 32 * 1024 * 1024:
                raise SharingError(413, "Publication exceeds 32 MiB")
            try:
                for experiment in body.experiments:
                    conn.execute(
                        "INSERT INTO publication_objects VALUES (?, 'experiment', ?, '', ?)",
                        (version_id, experiment.id, experiment.model_dump_json()),
                    )
                for run in body.runs:
                    conn.execute(
                        "INSERT INTO publication_objects VALUES (?, 'run', ?, ?, ?)",
                        (version_id, run.id, run.experiment_id, run.model_dump_json()),
                    )
            except sqlite3.IntegrityError as exc:
                raise SharingError(409, "Duplicate publication object") from exc
            conn.execute(
                "INSERT INTO publication_batches VALUES (?, ?, ?)", (version_id, batch_id, digest)
            )

    def commit_publication(self, credential: str, version_id: str) -> dict[str, object]:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential)
            # A retried successful commit must not reactivate a stopped project
            # or roll its pointer back over a subsequent publication.
            already = conn.execute(
                "SELECT v.project_id, v.committed_at FROM publications v JOIN shared_projects p "
                "ON p.id = v.project_id WHERE v.id = ? AND p.source_id = ?",
                (version_id, source["id"]),
            ).fetchone()
            if already and already["committed_at"]:
                return {"project_id": already["project_id"], "version_id": version_id}
            draft = self._draft(conn, credential, version_id)
            if (
                draft["base_version"] != draft["current_version"]
                or draft["base_generation"] != draft["current_generation"]
            ):
                raise SharingError(409, "Publication base version changed")
            orphan = conn.execute(
                "SELECT 1 FROM publication_objects r WHERE r.version_id = ? AND r.kind = 'run' "
                "AND NOT EXISTS (SELECT 1 FROM publication_objects e WHERE e.version_id = r.version_id "
                "AND e.kind = 'experiment' AND e.entity_id = r.parent_id)",
                (version_id,),
            ).fetchone()
            if orphan:
                raise SharingError(422, "Published runs require their published experiment")
            now = datetime.now(UTC).isoformat()
            conn.execute("UPDATE publications SET committed_at = ? WHERE id = ?", (now, version_id))
            conn.execute(
                "UPDATE shared_projects SET current_version = ?, active = 1 WHERE id = ?",
                (version_id, draft["project_id"]),
            )
            self._audit(conn, source["principal_id"], "publication.committed", version_id)
            # Retain current/previous payloads and old idempotency receipts.
            obsolete = (
                "SELECT id FROM publications WHERE project_id = ? AND committed_at IS NOT NULL "
                "ORDER BY committed_at DESC, id DESC LIMIT -1 OFFSET 2"
            )
            conn.execute(
                "DELETE FROM publication_objects WHERE version_id IN (" + obsolete + ")",
                (draft["project_id"],),
            )
            conn.execute(
                "DELETE FROM publication_batches WHERE version_id IN (" + obsolete + ")",
                (draft["project_id"],),
            )
            return {"project_id": draft["project_id"], "version_id": version_id}

    def abort_publication(self, credential: str, version_id: str) -> None:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential)
            self._draft(conn, credential, version_id)
            conn.execute("DELETE FROM publication_objects WHERE version_id = ?", (version_id,))
            conn.execute("DELETE FROM publication_batches WHERE version_id = ?", (version_id,))
            conn.execute("DELETE FROM publications WHERE id = ?", (version_id,))
            self._audit(conn, source["principal_id"], "publication.aborted", version_id)

    def _project(
        self, conn: sqlite3.Connection, actor: str, project_id: str, *, owner: bool = False
    ) -> sqlite3.Row:
        self._actor(conn, actor)
        row = conn.execute("SELECT * FROM shared_projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise SharingError(404, "Project not found")
        owner_enabled = conn.execute(
            "SELECT 1 FROM principals WHERE id = ? AND disabled = 0", (row["owner_id"],)
        ).fetchone()
        if not owner_enabled:
            raise SharingError(404, "Project not found")
        if row["owner_id"] == actor:
            return row
        grant = conn.execute(
            "SELECT 1 FROM grants WHERE project_id = ? AND principal_id = ? AND revoked_at IS NULL",
            (project_id, actor),
        ).fetchone()
        if not grant or not row["active"]:
            raise SharingError(404, "Project not found")
        if owner:
            raise SharingError(403, "Project owner required")
        return row

    @staticmethod
    def _project_response(
        conn: sqlite3.Connection, project: sqlite3.Row, actor: str
    ) -> dict[str, object]:
        version = conn.execute(
            "SELECT project_json, committed_at FROM publications WHERE id = ?",
            (project["current_version"],),
        ).fetchone()
        owner = conn.execute(
            "SELECT display_name FROM principals WHERE id = ?", (project["owner_id"],)
        ).fetchone()
        source = conn.execute(
            "SELECT last_seen_at FROM sources WHERE id = ?", (project["source_id"],)
        ).fetchone()
        return {
            "id": project["id"],
            "project": json.loads(version["project_json"]) if version else None,
            "owner_id": project["owner_id"],
            "owner_name": owner["display_name"],
            "role": "owner" if project["owner_id"] == actor else "viewer",
            "active": bool(project["active"]),
            "version_id": project["current_version"],
            "published_at": version["committed_at"] if version else None,
            "source_seen_at": source["last_seen_at"],
        }

    def list_projects(self, actor: str, *, offset: int = 0, limit: int = 100) -> dict[str, object]:
        with self._transaction() as conn:
            self._actor(conn, actor)
            visible = (
                "FROM shared_projects p JOIN principals owner ON owner.id = p.owner_id "
                "WHERE owner.disabled = 0 AND (p.owner_id = ? OR (p.active = 1 AND EXISTS "
                "(SELECT 1 FROM grants g WHERE g.project_id = p.id AND g.principal_id = ? AND g.revoked_at IS NULL)) "
                ")"
            )
            total = conn.execute("SELECT COUNT(*) " + visible, (actor, actor)).fetchone()[0]
            rows = conn.execute(
                "SELECT p.* " + visible + " ORDER BY p.id LIMIT ? OFFSET ?",
                (actor, actor, limit, offset),
            ).fetchall()
            return {
                "items": [self._project_response(conn, row, actor) for row in rows],
                "total": total,
            }

    def get_project(self, actor: str, project_id: str) -> dict[str, object]:
        with self._transaction() as conn:
            return self._project_response(conn, self._project(conn, actor, project_id), actor)

    def objects(
        self, actor: str, project_id: str, kind: str, *, offset: int = 0, limit: int = 100
    ) -> dict[str, object]:
        with self._transaction() as conn:
            project = self._project(conn, actor, project_id)
            args = (project["current_version"], kind)
            total = conn.execute(
                "SELECT COUNT(*) FROM publication_objects WHERE version_id = ? AND kind = ?", args
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT body FROM publication_objects WHERE version_id = ? AND kind = ? "
                "ORDER BY parent_id, entity_id LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
            return {
                "items": [json.loads(row["body"]) for row in rows],
                "total": total,
                "version_id": project["current_version"],
            }

    def metrics(
        self, actor: str, project_id: str, experiment_id: str, run_id: str
    ) -> dict[str, object]:
        with self._transaction() as conn:
            project = self._project(conn, actor, project_id)
            row = conn.execute(
                "SELECT body FROM publication_objects WHERE version_id = ? AND kind = 'run' "
                "AND parent_id = ? AND entity_id = ?",
                (project["current_version"], experiment_id, run_id),
            ).fetchone()
            if row is None:
                raise SharingError(404, "Run not found")
            return {
                "metrics": json.loads(row["body"])["metrics"],
                "version_id": project["current_version"],
            }

    def stop_publication(self, actor: str, project_id: str) -> None:
        with self._transaction(write=True) as conn:
            self._project(conn, actor, project_id, owner=True)
            conn.execute(
                "UPDATE shared_projects SET active = 0, generation = generation + 1 WHERE id = ?",
                (project_id,),
            )
            self._audit(conn, actor, "publication.stopped", project_id)
            conn.execute(
                "UPDATE asset_shares SET state = 'revoking', updated_at = ? "
                "WHERE project_id = ? AND state IN ('preparing', 'active')",
                (datetime.now(UTC).isoformat(), project_id),
            )

    def invite(self, actor: str, project_id: str, recipient_id: str) -> dict[str, object]:
        with self._transaction(write=True) as conn:
            self._project(conn, actor, project_id, owner=True)
            if actor == recipient_id:
                raise SharingError(422, "Owner already has access")
            recipient = conn.execute(
                "SELECT id FROM principals WHERE id = ? AND disabled = 0", (recipient_id,)
            ).fetchone()
            if recipient is None:
                raise SharingError(422, "Recipient is not available")
            now = datetime.now(UTC)
            conn.execute(
                "UPDATE invitations SET status = 'revoked' WHERE project_id = ? AND recipient_id = ? "
                "AND status = 'pending' AND expires_at <= ?",
                (project_id, recipient_id, now.isoformat()),
            )
            existing = conn.execute(
                "SELECT * FROM invitations WHERE project_id = ? AND recipient_id = ? AND status = 'pending'",
                (project_id, recipient_id),
            ).fetchone()
            if existing:
                return dict(existing)
            invitation_id = generate_uuid7()
            conn.execute(
                "INSERT INTO invitations VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (
                    invitation_id,
                    project_id,
                    recipient_id,
                    actor,
                    now.isoformat(),
                    (now + timedelta(days=7)).isoformat(),
                ),
            )
            self._audit(conn, actor, "invitation.created", invitation_id)
            return dict(
                conn.execute("SELECT * FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
            )

    def invitations(self, actor: str) -> list[dict[str, object]]:
        with self._transaction() as conn:
            self._actor(conn, actor)
            result = []
            for row in conn.execute(
                "SELECT i.*, o.display_name AS owner_name, v.project_json FROM invitations i "
                "JOIN shared_projects p ON p.id = i.project_id JOIN principals o ON o.id = p.owner_id "
                "LEFT JOIN publications v ON v.id = p.current_version WHERE i.recipient_id = ? ORDER BY i.id",
                (actor,),
            ):
                invitation = dict(row)
                published = invitation.pop("project_json")
                invitation["project_name"] = json.loads(published)["name"] if published else None
                result.append(invitation)
            return result

    def respond(self, actor: str, invitation_id: str, *, accept: bool) -> None:
        with self._transaction(write=True) as conn:
            self._actor(conn, actor)
            row = conn.execute(
                "SELECT * FROM invitations WHERE id = ? AND recipient_id = ?",
                (invitation_id, actor),
            ).fetchone()
            if row is None:
                raise SharingError(404, "Invitation not found")
            if row["status"] != "pending":
                raise SharingError(409, "Invitation is no longer pending")
            if accept and datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
                raise SharingError(410, "Invitation expired")
            owner = conn.execute(
                "SELECT owner_id FROM shared_projects WHERE id = ?", (row["project_id"],)
            ).fetchone()
            if (
                accept
                and not conn.execute(
                    "SELECT 1 FROM principals WHERE id = ? AND disabled = 0", (owner["owner_id"],)
                ).fetchone()
            ):
                raise SharingError(410, "Invitation is no longer available")
            if accept:
                conn.execute(
                    "INSERT INTO grants VALUES (?, ?, 'viewer', ?, NULL) "
                    "ON CONFLICT(project_id, principal_id) DO UPDATE SET revoked_at = NULL, created_at = excluded.created_at",
                    (row["project_id"], actor, datetime.now(UTC).isoformat()),
                )
            conn.execute(
                "UPDATE invitations SET status = ? WHERE id = ?",
                ("accepted" if accept else "declined", invitation_id),
            )
            self._audit(
                conn,
                actor,
                "invitation.accepted" if accept else "invitation.declined",
                invitation_id,
            )

    def revoke_invitation(self, actor: str, invitation_id: str) -> None:
        with self._transaction(write=True) as conn:
            row = conn.execute(
                "SELECT * FROM invitations WHERE id = ?", (invitation_id,)
            ).fetchone()
            if row is None:
                raise SharingError(404, "Invitation not found")
            self._project(conn, actor, row["project_id"], owner=True)
            if row["status"] != "pending":
                raise SharingError(409, "Invitation is no longer pending")
            conn.execute(
                "UPDATE invitations SET status = 'revoked' WHERE id = ? AND status = 'pending'",
                (invitation_id,),
            )
            self._audit(conn, actor, "invitation.revoked", invitation_id)

    def members(self, actor: str, project_id: str) -> dict[str, object]:
        with self._transaction() as conn:
            self._project(conn, actor, project_id, owner=True)
            grants = [
                dict(row)
                for row in conn.execute(
                    "SELECT g.*, p.display_name FROM grants g JOIN principals p ON p.id = g.principal_id "
                    "WHERE g.project_id = ? AND g.revoked_at IS NULL",
                    (project_id,),
                )
            ]
            invitations = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM invitations WHERE project_id = ? AND status = 'pending'",
                    (project_id,),
                )
            ]
            return {"members": grants, "invitations": invitations}

    def revoke_member(self, actor: str, project_id: str, recipient_id: str) -> None:
        with self._transaction(write=True) as conn:
            if actor == recipient_id:
                self._actor(conn, actor)
                project = conn.execute(
                    "SELECT * FROM shared_projects WHERE id = ?", (project_id,)
                ).fetchone()
                grant = conn.execute(
                    "SELECT 1 FROM grants WHERE project_id = ? AND principal_id = ? AND revoked_at IS NULL",
                    (project_id, actor),
                ).fetchone()
                if project is None or (project["owner_id"] != actor and not grant):
                    raise SharingError(404, "Project not found")
            else:
                project = self._project(conn, actor, project_id, owner=True)
            if recipient_id == project["owner_id"]:
                raise SharingError(422, "Owner cannot leave their project")
            conn.execute(
                "UPDATE grants SET revoked_at = ? WHERE project_id = ? AND principal_id = ?",
                (datetime.now(UTC).isoformat(), project_id, recipient_id),
            )
            # A previously issued pending invitation must not undo revocation.
            conn.execute(
                "UPDATE invitations SET status = 'revoked' WHERE project_id = ? AND recipient_id = ? AND status = 'pending'",
                (project_id, recipient_id),
            )
            self._audit(conn, actor, "member.revoked", f"{project_id}:{recipient_id}")
            conn.execute(
                "UPDATE asset_shares SET state = 'revoking', updated_at = ? "
                "WHERE project_id = ? AND recipient_id = ? AND state IN ('preparing', 'active')",
                (datetime.now(UTC).isoformat(), project_id, recipient_id),
            )

    def prepare_asset(self, credential: str, body: PrepareAssetShare) -> dict[str, object]:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential)
            project = conn.execute(
                "SELECT * FROM shared_projects WHERE source_id = ? AND workspace_id = ? AND project_id = ?",
                (source["id"], body.workspace_id, body.project_id),
            ).fetchone()
            if project is None or not project["active"]:
                raise SharingError(409, "Publish the project before sharing its assets")
            if project["owner_id"] == body.recipient_id:
                raise SharingError(422, "Choose a project viewer as the asset recipient")
            self._project(conn, body.recipient_id, project["id"])
            binding = conn.execute(
                "SELECT uid FROM principal_bindings WHERE principal_id = ? AND cluster_id = ?",
                (body.recipient_id, source["cluster_id"]),
            ).fetchone()
            if binding is None:
                raise SharingError(422, "Recipient needs a Linux identity on this cluster")
            pending = conn.execute(
                "SELECT COUNT(*) FROM asset_shares WHERE source_id = ? AND state = 'preparing'",
                (source["id"],),
            ).fetchone()[0]
            if pending >= 32:
                raise SharingError(429, "Too many unfinished asset publications")
            asset_id, now = generate_uuid7(), datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO asset_shares VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'preparing', ?, ?)",
                (
                    asset_id,
                    project["id"],
                    source["id"],
                    body.asset_id,
                    body.recipient_id,
                    body.title,
                    body.digest,
                    body.size,
                    source["uid"],
                    binding["uid"],
                    source["cluster_id"],
                    body.storage_id,
                    now,
                    now,
                ),
            )
            self._audit(conn, source["principal_id"], "asset.prepared", asset_id)
            row = conn.execute("SELECT * FROM asset_shares WHERE id = ?", (asset_id,)).fetchone()
            return {key: row[key] for key in AssetTransfer.model_fields}

    def list_assets(
        self, actor: str, project_id: str, *, offset: int = 0, limit: int = 100
    ) -> dict[str, object]:
        with self._transaction() as conn:
            project = self._project(conn, actor, project_id)
            where = "project_id = ?"
            args: list[object] = [project_id]
            if project["owner_id"] != actor:
                where += " AND recipient_id = ? AND state = 'active'"
                args.append(actor)
            total = conn.execute(
                f"SELECT COUNT(*) FROM asset_shares WHERE {where}", args
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM asset_shares WHERE {where} ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
            return {
                "items": [{key: row[key] for key in AssetShare.model_fields} for row in rows],
                "total": total,
            }

    def revoke_asset(self, actor: str, asset_share_id: str) -> None:
        with self._transaction(write=True) as conn:
            row = conn.execute(
                "SELECT * FROM asset_shares WHERE id = ?", (asset_share_id,)
            ).fetchone()
            if row is None:
                raise SharingError(404, "Asset share not found")
            self._project(conn, actor, row["project_id"], owner=True)
            conn.execute(
                "UPDATE asset_shares SET state = 'revoking', updated_at = ? WHERE id = ? AND state != 'revoked'",
                (datetime.now(UTC).isoformat(), asset_share_id),
            )
            self._audit(conn, actor, "asset.revocation_requested", asset_share_id)

    def commit_asset(self, credential: str, asset_share_id: str) -> dict[str, object]:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential)
            row = conn.execute(
                "SELECT * FROM asset_shares WHERE id = ? AND source_id = ?",
                (asset_share_id, source["id"]),
            ).fetchone()
            if row is None:
                raise SharingError(404, "Asset share not found")
            self._project(conn, row["recipient_id"], row["project_id"])
            if row["state"] not in {"preparing", "active"}:
                raise SharingError(409, "Asset publication was revoked")
            conn.execute(
                "UPDATE asset_shares SET state = 'active', updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), asset_share_id),
            )
            self._audit(conn, source["principal_id"], "asset.published", asset_share_id)
            updated = conn.execute(
                "SELECT * FROM asset_shares WHERE id = ?", (asset_share_id,)
            ).fetchone()
            return {key: updated[key] for key in AssetShare.model_fields}

    def asset_access(self, credential: str, asset_share_id: str) -> dict[str, object]:
        with self._transaction() as conn:
            source = self._source(conn, credential)
            row = conn.execute(
                "SELECT a.* FROM asset_shares a JOIN sources s ON s.id = a.source_id "
                "WHERE a.id = ? AND a.recipient_id = ? AND a.recipient_uid = ? "
                "AND a.cluster_id = ? AND a.state = 'active' AND s.disabled = 0",
                (asset_share_id, source["principal_id"], source["uid"], source["cluster_id"]),
            ).fetchone()
            if row is None:
                raise SharingError(404, "Asset share not found")
            self._project(conn, source["principal_id"], row["project_id"])
            return {key: row[key] for key in AssetTransfer.model_fields}

    def asset_cleanup(self, credential: str, *, after_id: str = "") -> dict[str, object]:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential, cleanup_only=True)
            now = datetime.now(UTC)
            # Reconcile stopped projects, membership/identity revocations, and
            # abandoned preparations even if the owner UI never reconnects.
            conn.execute(
                "UPDATE asset_shares SET state = 'revoking', updated_at = ? "
                "WHERE source_id = ? AND state IN ('preparing', 'active') AND ("
                "(state = 'preparing' AND created_at < ?) OR EXISTS ("
                "SELECT 1 FROM shared_projects p JOIN principals o ON o.id = p.owner_id "
                "JOIN principals r ON r.id = asset_shares.recipient_id "
                "JOIN sources s ON s.id = asset_shares.source_id "
                "WHERE p.id = asset_shares.project_id AND (p.active = 0 OR o.disabled = 1 "
                "OR r.disabled = 1 OR s.disabled = 1 OR NOT EXISTS ("
                "SELECT 1 FROM grants g WHERE g.project_id = p.id "
                "AND g.principal_id = asset_shares.recipient_id AND g.revoked_at IS NULL))))",
                (now.isoformat(), source["id"], (now - timedelta(hours=1)).isoformat()),
            )
            rows = conn.execute(
                "SELECT * FROM asset_shares WHERE source_id = ? AND state = 'revoking' AND id > ? ORDER BY id LIMIT 100",
                (source["id"], after_id),
            ).fetchall()
            return {
                "items": [{key: row[key] for key in AssetTransfer.model_fields} for row in rows]
            }

    def finish_asset_cleanup(self, credential: str, asset_share_id: str) -> None:
        with self._transaction(write=True) as conn:
            source = self._source(conn, credential, cleanup_only=True)
            row = conn.execute(
                "SELECT * FROM asset_shares WHERE id = ? AND source_id = ?",
                (asset_share_id, source["id"]),
            ).fetchone()
            if row is None:
                raise SharingError(404, "Asset share not found")
            # Also used by a failed publisher to abandon its preparation.
            if row["state"] == "revoked":
                return
            conn.execute(
                "UPDATE asset_shares SET state = 'revoked', updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), asset_share_id),
            )
            self._audit(conn, source["principal_id"], "asset.filesystem_revoked", asset_share_id)
