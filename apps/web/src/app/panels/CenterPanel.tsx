import { Suspense } from "react";
import { LazySurface } from "@/app/layout/LazySurface";
import { SurfaceErrorBoundary } from "@/app/layout/SurfaceErrorBoundary";
import {
  getNavigationContribution,
  type NavigationEmptySelection,
} from "@/app/navigation/sections";
import type { InspectorSurfaceRegistration } from "@/app/panels/inspectorSurface";
import { resolveRenderersForSelection } from "@/app/registry";
import type { InspectorTarget, LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { usePluginPreferencesGeneration } from "@/plugins/preferences";

const DEFAULT_EMPTY_SELECTION_COPY: NavigationEmptySelection = {
  title: "Select an item to begin",
  description: "Choose an item from the explorer to open its workspace.",
};

const EmptySelectionPlaceholder = ({ copy }: { copy?: NavigationEmptySelection }): JSX.Element => {
  const content = copy ?? DEFAULT_EMPTY_SELECTION_COPY;
  return (
    <div className="flex h-full items-center justify-center p-6">
      <WorkbenchOperationState kind="empty" title={content.title} detail={content.description} />
    </div>
  );
};

interface CenterPanelProps {
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  leftPanelView?: LeftPanelView;
  inspectorTarget: InspectorTarget;

  onInspectorTargetChange: (target: InspectorTarget) => void;
  onInspectorChange: (registration: InspectorSurfaceRegistration | null) => void;
  onRefresh: () => void;
}

export const CenterPanel = ({
  selection,
  snapshot,
  leftPanelView,
  inspectorTarget,
  onInspectorTargetChange,
  onInspectorChange,
  onRefresh,
}: CenterPanelProps): JSX.Element => {
  // Plugin enable flags gate contributions — re-resolve when toggled.
  usePluginPreferencesGeneration();
  // Optional built-ins register after first render without requiring navigation.
  useContributionGeneration();

  if (!selection) {
    const navigation = leftPanelView ? getNavigationContribution(leftPanelView) : undefined;
    const Landing = navigation?.landing;
    if (Landing) {
      return (
        <SurfaceErrorBoundary
          resetKey={`landing:${navigation.id}`}
          fallback={(error) => (
            <div className="flex h-full items-center justify-center p-6">
              <WorkbenchOperationState
                kind="error"
                title="Could not load this view"
                detail={error.message}
                action={
                  <WorkbenchRetryAction
                    label="Reload application"
                    onClick={() => window.location.reload()}
                  />
                }
              />
            </div>
          )}
        >
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center p-6">
                <WorkbenchOperationState kind="loading" title="Loading view" />
              </div>
            }
          >
            <Landing
              snapshot={snapshot}
              onRefresh={onRefresh}
              onInspectorChange={onInspectorChange}
            />
          </Suspense>
        </SurfaceErrorBoundary>
      );
    }
    return <EmptySelectionPlaceholder copy={navigation?.emptySelection} />;
  }

  const renderers = resolveRenderersForSelection(selection, snapshot, "center");

  if (renderers.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <WorkbenchOperationState
          kind="empty"
          title="Viewer unavailable"
          detail="No enabled panel plugin owns this surface. Turn a plugin back on in Settings → UI plugins."
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {renderers.map((renderer) => (
        <LazySurface
          key={renderer.id}
          resetKey={`renderer:${renderer.id}:${selection.objectId}`}
          loadingTitle={`Loading ${renderer.title}…`}
          errorTitle={`Could not load ${renderer.title}`}
        >
          <renderer.Component
            selection={selection}
            snapshot={snapshot}
            inspectorTarget={inspectorTarget}
            onInspectorTargetChange={onInspectorTargetChange}
            onRefresh={onRefresh}
          />
        </LazySurface>
      ))}
    </div>
  );
};
