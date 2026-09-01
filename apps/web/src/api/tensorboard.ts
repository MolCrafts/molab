import { apiErrorMessage } from "@/api/errors";
import { ApiError } from "@/api/generated/core/ApiError";
import type { TensorboardScalarPoint } from "@/api/generated/models/TensorboardScalarPoint";
import type { TensorboardScalarSeries as GeneratedTensorboardScalarSeries } from "@/api/generated/models/TensorboardScalarSeries";
import { TensorboardService } from "@/api/generated/services/TensorboardService";

export type { TensorboardScalarPoint } from "@/api/generated/models/TensorboardScalarPoint";

export type TensorboardScalarSeries = {
  logdir: string;
  points: TensorboardScalarPoint[];
  tag: string;
};

export type TensorboardScalarsResponse = {
  logdirs: string[];
  runDir: string;
  runId: string;
  series: TensorboardScalarSeries[];
};

/** HTTP status preserved so the tab can treat 503 as "extra not installed". */
export class TensorboardScalarsError extends Error {
  public readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "TensorboardScalarsError";
    this.status = status;
  }
}

const withPoints = (series: GeneratedTensorboardScalarSeries[]): TensorboardScalarSeries[] =>
  series.map((row) => ({
    logdir: row.logdir,
    tag: row.tag,
    points: row.points ?? [],
  }));

export const tensorboardApi = {
  getRunTensorboardScalars: async (
    projectId: string,
    experimentId: string,
    runId: string,
    opts: { tag?: string[]; logdir?: string } = {},
  ): Promise<TensorboardScalarsResponse> => {
    try {
      const data = await TensorboardService.getRunTensorboardScalars(
        projectId,
        experimentId,
        runId,
        opts.tag,
        opts.logdir,
      );
      return {
        ...data,
        logdirs: data.logdirs ?? [],
        series: withPoints(data.series ?? []),
      };
    } catch (err) {
      if (err instanceof ApiError) {
        throw new TensorboardScalarsError(
          err.status,
          apiErrorMessage(err, "Failed to fetch tensorboard scalars"),
        );
      }
      throw err;
    }
  },
};
