import { Button, Label } from "@molcrafts/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { sharingApi } from "@/api/sharing";
import type { Principal, SharedProject } from "@/api/sharing-generated";
import { formatBytes } from "@/lib/format-bytes";

export function AssetSharingPanel({
  principal,
  project,
}: {
  principal: Principal;
  project: SharedProject;
}): JSX.Element {
  const [offset, setOffset] = useState(0);
  const client = useQueryClient();
  const assets = useQuery({
    queryKey: ["sharing", principal.id, project.id, "assets", offset],
    queryFn: ({ signal }) => sharingApi.assets(project.id, offset, signal),
    refetchInterval: 3000,
    retry: false,
    gcTime: 0,
  });
  const revoke = useMutation({
    gcTime: 0,
    mutationFn: sharingApi.revokeAsset,
    onSuccess: () => client.invalidateQueries({ queryKey: ["sharing", principal.id, project.id] }),
  });
  return (
    <section className="my-8 space-y-4" aria-label="Shared files">
      <h2 className="font-medium">Shared files</h2>
      <p className="text-label text-muted-foreground">
        Each file is a published snapshot. Downloads use your own cluster account and require both
        project access and Linux file permission.
      </p>
      {project.role === "owner" && project.active && project.project && (
        <AssetPublicationForm principal={principal} project={project} />
      )}
      {revoke.isError && <p role="alert">{revoke.error.message}</p>}
      {assets.isError ? (
        <p role="alert">{assets.error.message}</p>
      ) : assets.isPending ? (
        <p role="status">Loading shared files…</p>
      ) : (
        <>
          {assets.data.items.length === 0 && (
            <p className="text-muted-foreground">No files have been shared with this view.</p>
          )}
          <ul className="divide-y border-y">
            {assets.data.items.map((asset) => (
              <li key={asset.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="break-words font-medium">{asset.title}</p>
                  <p className="text-label text-muted-foreground">
                    {formatBytes(asset.size)} · {asset.state}
                  </p>
                  <p className="break-all font-mono text-label text-muted-foreground">
                    {asset.digest}
                  </p>
                  {project.role === "owner" && (
                    <p className="break-all text-label text-muted-foreground">
                      Recipient: {asset.recipient_id}
                    </p>
                  )}
                  {asset.state === "revoking" && (
                    <p className="mt-1 text-label" role="status">
                      Molab downloads are blocked. Linux access awaits removal by your user service.
                    </p>
                  )}
                </div>
                {project.role === "viewer" && asset.state === "active" && (
                  <a
                    className="rounded-md border px-3 py-2 text-label hover:bg-muted focus-visible:outline focus-visible:outline-primary"
                    href={`/api/sharing/worker/assets/${encodeURIComponent(asset.id)}/download`}
                    download
                  >
                    Download
                  </a>
                )}
                {project.role === "owner" &&
                  (asset.state === "active" || asset.state === "preparing") && (
                    <Button
                      variant="outline"
                      disabled={revoke.isPending}
                      onClick={() => revoke.mutate(asset.id)}
                    >
                      Revoke file access
                    </Button>
                  )}
              </li>
            ))}
          </ul>
          {assets.data.total > 100 && (
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous
              </Button>
              <span className="text-label">
                {offset + 1}–{offset + assets.data.items.length} of {assets.data.total}
              </span>
              <Button
                variant="outline"
                disabled={offset + 100 >= assets.data.total}
                onClick={() => setOffset(offset + 100)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function AssetPublicationForm({
  principal,
  project,
}: {
  principal: Principal;
  project: SharedProject;
}): JSX.Element {
  const [assetId, setAssetId] = useState("");
  const [recipientId, setRecipientId] = useState("");
  const client = useQueryClient();
  const capabilities = useQuery({
    queryKey: ["sharing", principal.id, "asset-capabilities"],
    queryFn: ({ signal }) => sharingApi.assetCapabilities(signal),
    retry: false,
    gcTime: 0,
  });
  const inventory = useQuery({
    queryKey: ["sharing", principal.id, project.id, "asset-inventory"],
    queryFn: ({ signal }) => sharingApi.assetInventory(project.project?.id ?? "", signal),
    enabled: capabilities.data?.enabled === true && !!project.project,
    retry: false,
    gcTime: 0,
  });
  const members = useQuery({
    queryKey: ["sharing", principal.id, project.id, "members"],
    queryFn: ({ signal }) => sharingApi.members(project.id, signal),
    refetchInterval: 3000,
    retry: false,
    gcTime: 0,
  });
  const selected = inventory.data?.find((asset) => asset.id === assetId);
  const recipients = members.data?.members.filter((member) => !member.revoked_at) ?? [];
  const publish = useMutation({
    gcTime: 0,
    mutationFn: async () => {
      if (!selected || !project.project || !recipientId)
        throw new Error("Choose a file and a recipient.");
      return sharingApi.shareAsset({
        project_id: project.project.id,
        asset_id: selected.id,
        recipient_id: recipientId,
        digest: selected.digest,
      });
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["sharing", principal.id, project.id] }),
  });
  if (capabilities.isPending) return <p role="status">Checking file sharing availability…</p>;
  if (capabilities.isError || !capabilities.data.enabled) {
    return (
      <p className="text-label text-muted-foreground">
        File publishing requires asset storage configured by your cluster administrator.
      </p>
    );
  }
  return (
    <form
      className="space-y-3 rounded-md border p-4"
      onSubmit={(event) => {
        event.preventDefault();
        publish.mutate();
      }}
    >
      <fieldset disabled={publish.isPending} className="space-y-3">
        <legend className="mb-2 font-medium">Publish a file to a project viewer</legend>
        <div>
          <Label htmlFor="share-asset">Registered asset</Label>
          <select
            id="share-asset"
            required
            value={assetId}
            className="mt-1 block h-9 w-full rounded-md border bg-background px-3"
            onChange={(event) => {
              setAssetId(event.target.value);
              publish.reset();
            }}
          >
            <option value="">Choose a file</option>
            {inventory.data?.map((asset) => (
              <option key={asset.id} value={asset.id} disabled={asset.kind !== "file"}>
                {asset.title} · {formatBytes(asset.size)}
                {asset.kind === "directory" ? " · package as an archive first" : ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="share-asset-recipient">Recipient</Label>
          <select
            id="share-asset-recipient"
            required
            value={recipientId}
            className="mt-1 block h-9 w-full rounded-md border bg-background px-3"
            onChange={(event) => {
              setRecipientId(event.target.value);
              publish.reset();
            }}
          >
            <option value="">Choose a viewer who has accepted your invitation</option>
            {recipients.map((member) => (
              <option key={member.principal_id} value={member.principal_id}>
                {member.display_name}
              </option>
            ))}
          </select>
        </div>
        {selected && (
          <div className="space-y-1 text-label">
            <p>
              {selected.title} · {formatBytes(selected.size)} · Read only
            </p>
            <p className="break-all font-mono">{selected.digest}</p>
            <p className="text-muted-foreground">
              Review this file for credentials, private data and sensitive logs before publishing.
            </p>
          </div>
        )}
        {capabilities.data.backend === "group" && (
          <p role="note" className="text-label">
            Native Linux access includes every member of sharing group {capabilities.data.group_id}.
          </p>
        )}
        <Button
          type="submit"
          disabled={
            !selected ||
            selected.kind !== "file" ||
            !recipientId ||
            !recipients.some((member) => member.principal_id === recipientId)
          }
        >
          {publish.isPending ? "Publishing file…" : "Publish this snapshot"}
        </Button>
      </fieldset>
      {inventory.isError && <p role="alert">{inventory.error.message}</p>}
      {members.isError && <p role="alert">{members.error.message}</p>}
      {publish.isError && <p role="alert">{publish.error.message}</p>}
      {publish.isSuccess && (
        <p role="status">
          The selected snapshot is shared. Later file changes require a new publication.
        </p>
      )}
    </form>
  );
}
