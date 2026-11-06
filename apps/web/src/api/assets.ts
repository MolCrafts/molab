import type { ManagedAssetResponse } from "@/api/generated/models/ManagedAssetResponse";
import { ProjectsService } from "@/api/generated/services/ProjectsService";
import type { ApiAssetResponse } from "@/app/types";

/** Where one asset's bytes came from, as a single cell. */
export const assetOriginText = (asset: {
  originKind?: string | null;
  runId?: string | null;
  executionId?: string | null;
  task?: string | null;
  uri?: string | null;
}): string => {
  if (asset.originKind === "execution") {
    const where = [asset.runId, asset.executionId, asset.task].filter(Boolean).join(" / ");
    return where || "execution";
  }
  if (asset.originKind === "import") return asset.uri || "import";
  return asset.originKind || "—";
};

export const projectAssetView = (asset: ManagedAssetResponse): ApiAssetResponse => ({
  id: asset.id,
  projectId: asset.projectId ?? "",
  title: asset.title,
  createdAt: asset.createdAt,
  name: asset.title,
  kind: asset.mediaType || "asset",
  path: asset.file,
  updatedAt: asset.createdAt,
  scopeKind: asset.projectId ? "project" : "workspace",
  scopeIds: asset.projectId ? [asset.projectId] : [],
  extra: {
    digest: asset.digest,
    size: asset.size,
    originKind: asset.originKind,
    runId: asset.runId ?? null,
    executionId: asset.executionId ?? null,
    task: asset.task ?? null,
    uri: asset.uri ?? null,
    mediaType: asset.mediaType ?? null,
    file: asset.file,
  },
  tags: {},
  hasPreviewSidecar: false,
  ref: asset.ref,
});

export const assetsApi = {
  listProjectAssets: async (projectId: string): Promise<ApiAssetResponse[]> =>
    (await ProjectsService.listProjectAssets(projectId)).map(projectAssetView),
  getProjectAsset: async (projectId: string, assetId: string): Promise<ApiAssetResponse> =>
    projectAssetView(await ProjectsService.getProjectAsset(projectId, assetId)),
  downloadUrl: (projectId: string, assetId: string): string =>
    `/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/download`,
};
