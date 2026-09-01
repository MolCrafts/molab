import { refFromSelection } from "@/app/entities/interop";
import { RelatedPanel } from "@/app/entities/RelatedPanel";
import { LazySurface } from "@/app/layout/LazySurface";
import { resolveRenderersForSelection } from "@/app/registry";
import type { InspectorTarget, Selection, WorkspaceSnapshot } from "@/app/types";
import { NodeInspector } from "@/components/workbench";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { usePluginPreferencesGeneration } from "@/plugins/preferences";

interface RightPanelProps {
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  inspectorTarget: InspectorTarget;
  onInspectorTargetChange: (target: InspectorTarget) => void;
  onRefresh: () => void;
}

export const RightPanel = ({
  selection,
  snapshot,
  inspectorTarget,
  onInspectorTargetChange,
  onRefresh,
}: RightPanelProps): JSX.Element => {
  usePluginPreferencesGeneration();
  useContributionGeneration();

  if (!selection) {
    return (
      <div className="flex h-full flex-col overflow-auto">
        <NodeInspector title="Inspector" empty emptyHint="Select an entity for details." />
      </div>
    );
  }

  const renderers = resolveRenderersForSelection(selection, snapshot, "right");

  return (
    <div className="flex h-full flex-col overflow-auto">
      {renderers.map((renderer) => (
        <LazySurface
          key={renderer.id}
          resetKey={`inspector:${renderer.id}:${selection.objectId}`}
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
      <RelatedPanel entity={refFromSelection(selection)} snapshot={snapshot} />
    </div>
  );
};
