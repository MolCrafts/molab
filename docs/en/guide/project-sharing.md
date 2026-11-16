# HPC Project sharing

Molab shares explicitly published Project metadata through a separate gateway.
Each private Workspace Service runs as its own Linux user. A Project Viewer grant
does not grant workspace access, file permissions, a terminal, or another user's
Slurm identity.

This deployment requires a site-managed authentication proxy such as Open
OnDemand. Use the ordinary `molab serve` command for existing local workflows.
The gateway never needs access to private workspace directories or SSH keys.
Version one expects a dedicated site origin with root-relative API/UI routes;
it is not a drop-in app under an arbitrary Open OnDemand PUN URL prefix.

## Provision the gateway

Install the updated package to get `molab-sharing`, or use
`python -m molab.sharing_cli` from an editable checkout without reinstalling.
This separate entry point avoids the ordinary CLI's plugin discovery.

Run the gateway as a dedicated unprivileged operator account. Create its state
directory with mode 0700 on **persistent local disk**, outside NFS/Lustre homes.
Database mount detection is diagnostic; the operator must confirm the storage
contract. The database and configuration must be owned by the service UID with
mode 0600. The configuration file must not be a symlink.

Example `/etc/molab-sharing/gateway.json`, readable only by the gateway account:

```json
{
  "issuer": "https://sso.example.edu",
  "public_origin": "https://molab.example.edu/",
  "proxy_key": "GENERATE-A-UNIQUE-RANDOM-GATEWAY-KEY-AT-LEAST-32-CHARACTERS",
  "state_dir": "/var/lib/molab-sharing",
  "local_state_confirmed": true
}
```

Use `secrets.token_urlsafe(32)` to generate each secret. Do not use the example
placeholder. Provision stable authentication-provider subjects, not display
names or unverified request headers:

```bash
molab-sharing principal-add --config /etc/molab-sharing/gateway.json \
  --issuer https://sso.example.edu --subject ALICE-IMMUTABLE-SUBJECT --name Alice
molab-sharing principal-add --config /etc/molab-sharing/gateway.json \
  --issuer https://sso.example.edu --subject BOB-IMMUTABLE-SUBJECT --name Bob
molab-sharing gateway --config /etc/molab-sharing/gateway.json --port 8080
```

Provisioning prints the stable Principal ID. Keep this ID when an account's
display name changes. A subject from another issuer is a different identity.

## Provision each private user service

Bind Alice's Principal ID to the cluster and her existing, non-root Linux UID:

```bash
molab-sharing source-add --config /etc/molab-sharing/gateway.json \
  --principal ALICE-PRINCIPAL-ID --cluster cluster-a --uid 1001 \
  --credential-file /var/lib/molab-sharing/alice-source.json
```

The source token is written to a new mode-0600 file, never printed. The operator
securely supplies the token to Alice's service configuration. It authorizes
publication only, not browsing or share management.

Example `~/.molab/sharing-worker.json`, owned by Alice with mode 0600:

```json
{
  "issuer": "https://sso.example.edu",
  "subject": "ALICE-IMMUTABLE-SUBJECT",
  "principal_id": "ALICE-PRINCIPAL-ID",
  "uid": 1001,
  "cluster_id": "cluster-a",
  "public_origin": "https://molab.example.edu/",
  "proxy_key": "GENERATE-A-DIFFERENT-RANDOM-ALICE-PROXY-KEY-32-CHARACTERS",
  "gateway_url": "https://molab.example.edu/",
  "source_token": "SOURCE-ID.SOURCE-TOKEN-FROM-PROVISIONING"
}
```

**Never give a worker the gateway proxy key.** Users can read their own worker
configuration. Every worker uses a different proxy key and accepts only its
configured subject. Startup checks the process UID and verifies the source's
Principal, UID, and cluster against the gateway.

Have Open OnDemand or the approved site launcher run, **as Alice**:

```bash
molab-sharing worker /project/alice/workspace \
  --config /home/alice/.molab/sharing-worker.json --port 8081
```

Molab neither elevates privileges nor launches another user's process. Both
commands bind only to loopback. `--uds /site/runtime/service.sock` selects a Unix
socket instead; the site must provision its directory and proxy access. Launch
one user service per process. The existing workspace resolution state is
process-scoped, so multiple users' apps must never share a Python process.

## Reverse-proxy contract

Authenticate every request through the site's existing identity provider. Strip
incoming identity/key headers, then set these from trusted proxy state:

| Route | Backend | Headers supplied by proxy |
|---|---|---|
| `/api/sharing/worker` and `/api/sharing/worker/*` | Authenticated user's worker | That worker's key and subject |
| Other `/api/sharing/*` | Sharing gateway | Gateway key and authenticated subject |
| `/internal/sharing/*` | Sharing gateway | Preserve source Bearer credential; do not derive user identity from it |
| Other `/api/*` | Authenticated user's worker | That worker's key and subject |
| `/shared`, `/publish`, UI static assets | Gateway's built UI | Site login/chrome as appropriate |

The subject-to-worker mapping must be controlled by the site, never by an owner
name, query parameter, URL supplied by the client, or forwarded client header.
Do not log proxy keys, source Authorization headers, or publication bodies.
Use HTTPS at the public origin and preserve browser Origin on proxied requests.
The gateway does not create a second password/session system; logout and account
switching remain part of the site's SSO interface. Disabling a sharing Principal
does not disable the underlying institutional or Linux account.

Open OnDemand's authentication frontend and per-user processes are the intended
reference: [architecture](https://osc.github.io/ood-documentation/latest/architecture.html).
Invitation and revocation semantics draw on scoped grants in
[JupyterHub](https://jupyterhub.readthedocs.io/en/latest/reference/sharing.html).

## Publish and invite

Build the existing UI with `npm run build:web`, then open `/publish` through the
site entry point. Choose a Project, experiments, runs, scalar parameter names,
and numeric metric names. Descriptions are opt-in. Review all values and publish.
If the preview changes before confirmation, review it again.

Open the resulting shared Project and invite a collaborator using their **My
sharing ID** from `/shared`. Invitations are bound to the intended Principal and
expire in seven days. Accepting an invitation requires login; the link/ID is not
an anonymous access token. No email is sent automatically.

The owner's service refreshes approved objects/fields every 15 seconds when
their published values change. New runs and fields require another review.
The gateway retains the last successful version while a worker is offline.
Viewers can see the publication time, experiments, run statuses, selected
parameters and numeric charts. Downloading files requires a separate Asset grant
and a user service with access to the configured publication filesystem.
Source heartbeats distinguish an offline worker from an unchanged publication.
Payloads retain the current and previous version; older commit receipts remain
for idempotency. Drafts expire after 24 hours, with at most four per Project and
32 per source. Known upload failures abort their drafts; interrupted connections
can leave drafts until expiry.

Removing a Viewer blocks subsequent reads and cancels outstanding invitations
to that recipient. Viewers can leave voluntarily. **Stop publishing** blocks
Viewer access, including in-flight refresh commits; resuming requires another
owner-confirmed publication. Previously returned data cannot be recalled.
Deleting original workspace files does not revoke a published copy: stop the
publication explicitly.

## Operations and verification

`principal-disable` disables the Principal in the sharing control plane;
`source-disable` revokes a publisher credential. Principals and UID bindings are
not recycled. Issue a new source token when rotating a publisher, deploy it to
the user's service, then revoke the previous source. A new source creates new
Project identities and does not inherit the previous source's grants.

The SQLite database contains authoritative grants and transactional audit events.
Stop the gateway before a filesystem backup, or use SQLite's online backup API;
do not copy a database while it is being modified. Restore only a coordinated,
trusted control-plane backup: restoring an older authorization database can
restore older grants. Validate the schema version and reapply revocations before
reopening access. Workspace/Git backups never restore grants.

Regenerate sharing wire types with `npm run generate:sharing`. The checked-in
`sharing.openapi.json` and `src/api/sharing-generated` models are separate from
the private Workspace API contract.

```bash
uv run pytest tests/test_services/test_sharing.py tests/test_server/test_sharing.py \
  tests/test_server/test_sharing_worker.py -q
```

Linux CI additionally runs the dedicated multi-UID test with root only to create
two disposable test identities. Production Molab never runs its workers as root.
Site acceptance must separately verify real SSO subjects, per-backend proxy keys,
socket accessibility, storage, and Alice/Bob isolation on the target cluster.

## Share registered files

Asset sharing is optional. Metadata-only deployments keep working without an
`asset_storage` configuration. Configure the same Linux shared mount in each
participating user's private worker configuration:

```json
{
  "asset_storage": {
    "root": "/shared/molab-publications",
    "backend": "auto",
    "max_file_bytes": 1099511627776
  }
}
```

The administrator provisions the root, its traversal permissions and a directory
named after each user's numeric UID. For example, provision the root with mode
0711 and `/shared/molab-publications/1001` owned by UID 1001 with mode 0711.
Users need write permission only inside their own UID directory. All ancestors
must prevent replacement by other users. A site may alternatively provision a
root-owned sticky allocation directory; a pre-created UID directory must still
belong to its matching user. Do not put this root inside a private Workspace.
The gateway does not need the mount.

`auto` first checks for native NFSv4 ACL support, then uses POSIX ACL tools.
The POSIX backend requires `getfacl` and `setfacl`. The NFSv4 backend requires
`nfs4_getfacl`, `nfs4_setfacl` and a configured `nfsv4_domain`; it resolves each
recipient UID using the cluster's NSS and writes an ACL for `username@domain`.
The backend replaces inherited ACLs on new copies and rejects unsupported or
unexpected ACL representations. It never grants access by relaxing permissions
on an existing Workspace directory. See the upstream
[NFSv4 ACL tool manual](https://man7.org/linux/man-pages/man1/nfs4_setfacl.1.html).

Group mode must be selected explicitly with `backend: "group"`, `group_id`,
and `group_exposure_confirmed: true`. Both users must belong to the configured
group. Native filesystem access includes **all group members**; Molab's API
still requires the individually named Project and Asset grants. Group mode
requires POSIX ACL inspection/removal tools and is never an automatic fallback.

Publish Project metadata, invite the recipient and wait for them to accept.
In that shared Project's **Shared files** section, choose a registered file and
recipient, review its size and SHA-256 digest, and publish the snapshot. The
recipient also needs a provisioned Linux identity on the same cluster. This
initial implementation shares regular files; register a packaged archive to
share a directory. It rejects symbolic links and non-regular payloads.

The owner's service copies and hashes the file into
`<root>/<owner-uid>/<opaque-share-uuid>/payload`, then grants read access to the
copy. Original files and later replacements of the same Asset slot do not alter
the snapshot. The recipient downloads through their own Workspace Service;
that process opens the file with its own UID, without following symlinks. A
Project Viewer grant alone never exposes a file or the owner's terminal.

Revoking a file, removing a member, stopping a Project publication or disabling
an owner/source blocks new Molab downloads immediately. The owner's service
removes the published copy and acknowledges filesystem revocation in the
background. **Revoking** means native access still awaits cleanup; **revoked**
means the copy has been removed. An offline owner service delays Linux-level
cleanup. Existing downloads, already-open file descriptors and copied bytes
cannot be recalled. Cleanup-only source authentication remains available after
source/Principal disablement, without allowing publication or downloads.
Do not retire the owner service until its pending filesystem revocations finish.
Keep the same publication-root path while grants exist; its identity is recorded
with each grant. A service configured for a different root cannot acknowledge
removal of old copies. Storage moves require completing revocation on the old
mount before retiring its configuration.

A private, atomic cleanup intent records each unfinished file publication.
Interrupted publications are removed on restart, including when a gateway
commit response was lost. Unfinished server preparations expire into cleanup
after one hour. Database schema v1 is migrated transactionally to v2 to add the
Asset catalog; the existing metadata publication and grant records are retained.

Editor grants, collaborative execution and Globus integration remain later work.
