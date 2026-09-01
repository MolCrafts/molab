import "./side-effects";

/**
 * Internal `workflow` UI plugin — owns the workflow entity center/right
 * surfaces and the workspace-file `workflow.json` graph preview.
 *
 * Previously registered by `core` via `registerDefaultRenderers`. As a
 * first-class plugin it can be user-toggled in Settings, and host panels
 * skip it when there is no workflow data (see ExperimentViewer).
 */

export { FlowgramCanvas, type FlowgramCanvasProps } from "./flowgram-canvas";
export {
  buildFlowgramDocument,
  buildWorkflowDocument,
  type FlowgramDocument,
  parseTaskGraphIr,
} from "./flowgram-document";
export { default } from "./plugin";
export type { TaskGraphJson, TaskNodeJson } from "./task-graph-ir";
