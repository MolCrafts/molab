import { Suspense } from "react";
import { LazySurface } from "@/app/layout/LazySurface";
import { SurfaceErrorBoundary } from "@/app/layout/SurfaceErrorBoundary";
import { getNavigationContribution } from "@/app/navigation/sections";
import { resolveRenderersForSelection } from "@/app/registry";
import { Watermark } from "@/app/shell/Watermark";
import type { InspectorTarget, LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { usePluginPreferencesGeneration } from "@/plugins/preferences";

interface CenterPanelProps {
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  leftPanelView?: LeftPanelView;
  inspectorTarget: InspectorTarget;

  onInspectorTargetChange: (target: InspectorTarget) => void;
  onRefresh: () => void;
}

export const CenterPanel = ({
  selection,
  snapshot,
  leftPanelView,
  inspectorTarget,
  onInspectorTargetChange,
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
            <Landing snapshot={snapshot} onRefresh={onRefresh} />
          </Suspense>
        </SurfaceErrorBoundary>
      );
    }
    // Nothing open (L00): the editor watermark, not a per-section placeholder.
    return <Watermark />;
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
          key={`${renderer.id}:${selection.objectId}`}
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
