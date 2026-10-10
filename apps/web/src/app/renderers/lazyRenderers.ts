import type { SemanticObjectType } from "@/app/types";
import { lazyWithPrefetch, prefetchLazy } from "@/lib/lazy-with-prefetch";

export const ProjectViewerLazy = lazyWithPrefetch(() =>
  import("./ProjectViewer").then((module) => ({ default: module.ProjectViewer })),
);
export const ExperimentViewerLazy = lazyWithPrefetch(() =>
  import("./ExperimentViewer").then((module) => ({ default: module.ExperimentViewer })),
);
export const RunViewerLazy = lazyWithPrefetch(() =>
  import("./RunViewer").then((module) => ({ default: module.RunViewer })),
);
export const AssetViewerLazy = lazyWithPrefetch(() =>
  import("./AssetViewer").then((module) => ({ default: module.AssetViewer })),
);
export const ImageViewerLazy = lazyWithPrefetch(() =>
  import("./ImageViewer").then((module) => ({ default: module.ImageViewer })),
);
export const TaskViewerLazy = lazyWithPrefetch(() =>
  import("./TaskViewer").then((module) => ({ default: module.TaskViewer })),
);
export const MetadataInspectorLazy = lazyWithPrefetch(() =>
  import("./MetadataInspector").then((module) => ({ default: module.MetadataInspector })),
);

const RENDERER_BY_TYPE: Partial<Record<SemanticObjectType, { prefetch: () => unknown }>> = {
  project: ProjectViewerLazy,
  experiment: ExperimentViewerLazy,
  run: RunViewerLazy,
  asset: AssetViewerLazy,
  task: TaskViewerLazy,
};

/** Warm the viewer chunk for a selection before the user clicks it. */
export const prefetchRenderer = (objectType: SemanticObjectType): void => {
  prefetchLazy(RENDERER_BY_TYPE[objectType]);
};
