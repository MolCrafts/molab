import { CatalogService } from "@/api/generated/services/CatalogService";

export const catalogApi = {
  catalogByPath: (path: string) => CatalogService.catalogByPath(path),
};
