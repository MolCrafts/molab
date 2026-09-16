import { type JSX, lazy, Suspense } from "react";
import {
  buildRendererKeyFromSelection,
  renderPlanByObjectType,
  resolveRenderer,
} from "@/app/registry";
import type { RunInspectorRegistration } from "@/app/runs/inspector/RunInspector";
import type { InspectorTarget, LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { WorkbenchOperationState } from "@/components/workbench";

// Full-panel pages reached from the left nav rather than from a selection.
// Each is its own chunk: the dashboards pull in chart and aggregation code that
// a session which never leaves the entity tree should not have to download.
const RunsPage = lazy(async () => ({
  default: (await import("@/app/runs/RunsPage")).RunsPage,
}));
const WorkflowsPage = lazy(async () => ({
  default: (await import("@/app/workflows/WorkflowsPage")).WorkflowsPage,
}));
const SettingsPage = lazy(async () => ({
  default: (await import("@/app/settings/SettingsPage")).SettingsPage,
}));

/** Full-panel loading surface shared by the lazy page chunks. */
const PageFallback = (): JSX.Element => (
  <div className="flex h-full items-center justify-center p-6">
    <WorkbenchOperationState kind="loading" title="Loading…" />
  </div>
);

interface EmptySelectionCopy {
  title: string;
  description: string;
}

// Per-view empty-selection copy — the placeholder must speak the language of
// the section the user is looking at, not always the Experiments tree.
const EMPTY_SELECTION_COPY: Partial<Record<LeftPanelView, EmptySelectionCopy>> = {
  agent: {
    title: "No agent task selected",
    description: "Select an agent task from the left, or start a new one.",
  },
  knowledge: {
    title: "No document selected",
    description: "Pick a note from the left, or create a new one.",
  },
};

const DEFAULT_EMPTY_SELECTION_COPY: EmptySelectionCopy = {
  title: "Select an item to begin",
  description:
    "Pick a project, experiment, run, or workflow from the left navigation, or open the Runs " +
    "view to inspect every execution across the workspace.",
};

/** Resolve the placeholder copy for a left-panel view (exported for tests). */
export const emptySelectionCopy = (view?: LeftPanelView): EmptySelectionCopy =>
  (view && EMPTY_SELECTION_COPY[view]) || DEFAULT_EMPTY_SELECTION_COPY;

const EmptySelectionPlaceholder = ({ view }: { view?: LeftPanelView }): JSX.Element => {
  const copy = emptySelectionCopy(view);
  return (
    <div className="flex h-full items-center justify-center p-6">
      <WorkbenchOperationState kind="empty" title={copy.title} detail={copy.description} />
    </div>
  );
};

interface CenterPanelProps {
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  leftPanelView?: LeftPanelView;
  inspectorTarget: InspectorTarget;

  onInspectorTargetChange: (target: InspectorTarget) => void;
  onRunInspectorChange: (registration: RunInspectorRegistration | null) => void;
}

export const CenterPanel = ({
  selection,
  snapshot,
  leftPanelView,
  inspectorTarget,
  onInspectorTargetChange,
  onRunInspectorChange,
}: CenterPanelProps): JSX.Element => {
  if (!selection) {
    if (leftPanelView === "runs") {
      return (
        <Suspense fallback={<PageFallback />}>
          <RunsPage snapshot={snapshot} onInspectorChange={onRunInspectorChange} />
        </Suspense>
      );
    }
    if (leftPanelView === "workflow") {
      return (
        <Suspense fallback={<PageFallback />}>
          <WorkflowsPage snapshot={snapshot} />
        </Suspense>
      );
    }
    if (leftPanelView === "settings") {
      return (
        <Suspense fallback={<PageFallback />}>
          <SettingsPage />
        </Suspense>
      );
    }
    return <EmptySelectionPlaceholder view={leftPanelView} />;
  }

  const plan = renderPlanByObjectType[selection.objectType];
  const renderers = plan.center.map((target) => {
    const key = buildRendererKeyFromSelection(selection, target);
    return resolveRenderer(key, { selection, snapshot, target });
  });

  return (
    <div className="flex h-full flex-col">
      {renderers.map((renderer) => (
        <renderer.Component
          key={`${renderer.title}-${renderer.panelSlot}`}
          selection={selection}
          snapshot={snapshot}
          inspectorTarget={inspectorTarget}
          onInspectorTargetChange={onInspectorTargetChange}
        />
      ))}
    </div>
  );
};
