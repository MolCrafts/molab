import type { CancelablePromise } from "@/api/generated/core/CancelablePromise";
import { OpenAPI } from "@/api/generated/core/OpenAPI";
import { request } from "@/api/generated/core/request";

export interface SweepSeedResponse {
  created: string[];
  skipped: number;
  cells: number;
}

/** Seed the missing cells of a grid. Does not dispatch them. */
export const sweepApi = {
  seed: (
    projectId: string,
    experimentId: string,
    axes: Record<string, Array<string | number>>,
  ): CancelablePromise<SweepSeedResponse> =>
    request(OpenAPI, {
      method: "POST",
      url: "/api/projects/{project_id}/experiments/{experiment_id}/sweep",
      path: {
        project_id: projectId,
        experiment_id: experimentId,
      },
      body: { axes },
      mediaType: "application/json",
      errors: {
        422: "Validation Error",
      },
    }),
};
