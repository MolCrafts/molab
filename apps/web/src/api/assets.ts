import { AssetsService } from "@/api/generated/services/AssetsService";

export const assetsApi = {
  listAssets: () => AssetsService.listAssets(),
  listRunAssets: (runId: string) => AssetsService.listAssets(undefined, undefined, runId),
  getAssetLineage: (assetId: string) => AssetsService.getAssetLineage(assetId),
};
