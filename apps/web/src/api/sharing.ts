import type {
  AssetInventoryItem,
  AssetShare,
  AssetShareRequest,
  AssetSharingCapabilities,
  InventoryProject,
  Invitation,
  PreviewResponse,
  Principal,
  ProjectMembers,
  PublicationReceipt,
  PublicationSelection,
  SharedPage_AssetShare_,
  SharedPage_PublishedExperiment_,
  SharedPage_PublishedRun_,
  SharedPage_SharedProject_,
  SharedProject,
} from "./sharing-generated";

/** All sharing data stays on the authenticated origin; no owner paths or URLs. */
export async function sharingRequest<T>(
  path: string,
  options: { method?: "GET" | "POST" | "DELETE"; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(`/api/sharing/${path}`, {
    method: options.method ?? "GET",
    credentials: "same-origin",
    cache: "no-store",
    signal: options.signal,
    headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail =
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail.slice(0, 500)
        : null;
    const message =
      response.status === 401
        ? "Sign in through your cluster to view shared projects."
        : response.status === 403
          ? "You do not have permission to perform this action."
          : response.status === 404
            ? "This share is no longer available."
            : response.status === 409
              ? "The data changed. Refresh the preview and try again."
              : response.status === 410
                ? "This invitation has expired. Ask the owner for a new invitation."
                : (detail ??
                  "The request could not be completed. Review your selection and try again.");
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  try {
    return await response.json();
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error("Sign in through your cluster and refresh this page.");
  }
}

export const sharingApi = {
  assets: (projectId: string, offset: number, signal?: AbortSignal) =>
    sharingRequest<SharedPage_AssetShare_>(
      `projects/${encodeURIComponent(projectId)}/assets?offset=${offset}`,
      { signal },
    ),
  assetCapabilities: (signal?: AbortSignal) =>
    sharingRequest<AssetSharingCapabilities>("worker/assets/capabilities", { signal }),
  assetInventory: (projectId: string, signal?: AbortSignal) =>
    sharingRequest<AssetInventoryItem[]>(
      `worker/projects/${encodeURIComponent(projectId)}/assets`,
      {
        signal,
      },
    ),
  shareAsset: (body: AssetShareRequest) =>
    sharingRequest<AssetShare>("worker/assets", { method: "POST", body }),
  revokeAsset: (id: string) =>
    sharingRequest<void>(`assets/${encodeURIComponent(id)}`, { method: "DELETE" }),
  me: (signal?: AbortSignal) => sharingRequest<Principal>("me", { signal }),
  projects: (offset: number, signal?: AbortSignal) =>
    sharingRequest<SharedPage_SharedProject_>(`projects?offset=${offset}`, { signal }),
  project: (id: string, signal?: AbortSignal) =>
    sharingRequest<SharedProject>(`projects/${encodeURIComponent(id)}`, { signal }),
  runs: (id: string, offset: number, signal?: AbortSignal) =>
    sharingRequest<SharedPage_PublishedRun_>(
      `projects/${encodeURIComponent(id)}/runs?offset=${offset}`,
      {
        signal,
      },
    ),
  experiments: (id: string, offset: number, signal?: AbortSignal) =>
    sharingRequest<SharedPage_PublishedExperiment_>(
      `projects/${encodeURIComponent(id)}/experiments?offset=${offset}`,
      { signal },
    ),
  invitations: (signal?: AbortSignal) => sharingRequest<Invitation[]>("invitations", { signal }),
  respond: (id: string, accept: boolean) =>
    sharingRequest<void>(`invitations/${encodeURIComponent(id)}/${accept ? "accept" : "decline"}`, {
      method: "POST",
    }),
  members: (id: string, signal?: AbortSignal) =>
    sharingRequest<ProjectMembers>(`projects/${encodeURIComponent(id)}/members`, { signal }),
  invite: (id: string, recipient: string) =>
    sharingRequest<Invitation>(`projects/${encodeURIComponent(id)}/invitations`, {
      method: "POST",
      body: { recipient_id: recipient, role: "viewer" },
    }),
  revokeInvitation: (id: string) =>
    sharingRequest<void>(`invitations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  remove: (id: string, recipient: string) =>
    sharingRequest<void>(
      `projects/${encodeURIComponent(id)}/members/${encodeURIComponent(recipient)}`,
      {
        method: "DELETE",
      },
    ),
  stop: (id: string) =>
    sharingRequest<void>(`projects/${encodeURIComponent(id)}/publication`, { method: "DELETE" }),
  inventory: (signal?: AbortSignal) =>
    sharingRequest<InventoryProject[]>("worker/inventory", { signal }),
  preview: (selection: PublicationSelection) =>
    sharingRequest<PreviewResponse>("worker/preview", { method: "POST", body: selection }),
  publish: (selection: PublicationSelection, digest: string) =>
    sharingRequest<PublicationReceipt>("worker/publish", {
      method: "POST",
      body: { selection, preview_digest: digest },
    }),
};
