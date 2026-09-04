import type { ManagedAssetResponse } from "@/api/generated/models/ManagedAssetResponse";
import type { AssetVersionResponse } from "@/api/generated/models/AssetVersionResponse";
import { ProjectsService } from "@/api/generated/services/ProjectsService";
import type { ApiAssetResponse } from "@/app/types";

export const projectAssetView = (asset: ManagedAssetResponse): ApiAssetResponse => ({
  ...asset,
  name: asset.title,
  kind: "asset",
  path: "",
  updatedAt: asset.createdAt,
  scopeKind: "project",
  scopeIds: [asset.projectId],
  extra: { versionCount: asset.versionCount ?? 0 },
  tags: {},
  hasPreviewSidecar: false,
});

export const assetsApi = {
  listProjectAssets: async (projectId: string): Promise<ApiAssetResponse[]> =>
    (await ProjectsService.listProjectAssets(projectId)).map(projectAssetView),
  getProjectAsset: async (projectId: string, assetId: string): Promise<ApiAssetResponse> =>
    projectAssetView(await ProjectsService.getProjectAsset(projectId, assetId)),
  listVersions: (projectId: string, assetId: string): Promise<AssetVersionResponse[]> =>
    ProjectsService.listProjectAssetVersions(projectId, assetId),
  downloadUrl: (projectId: string, assetId: string): string =>
    `/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/download`,
};
