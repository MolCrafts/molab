import { type ReactNode, Suspense } from "react";
import { SurfaceErrorBoundary } from "@/app/layout/SurfaceErrorBoundary";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import type { NavigationContribution, NavigationExplorerProps } from "./sections";

export interface NavigationExplorerHostProps {
  contribution: NavigationContribution;
  explorerProps: NavigationExplorerProps;
  actions?: ReactNode;
  blankMenu?: ReactNode;
  children?: ReactNode;
}

/** Product contribution host; shared ExplorerShell remains domain-free chrome. */
export const NavigationExplorerHost = ({
  contribution,
  explorerProps,
  actions,
  blankMenu,
  children,
}: NavigationExplorerHostProps): JSX.Element | null => {
  if (contribution.shellMode !== "explorer") return null;
  const FeatureExplorer = contribution.explorer;

  if (FeatureExplorer) {
    return (
      <SurfaceErrorBoundary
        resetKey={`explorer:${contribution.id}`}
        fallback={(error) => (
          <LeftExplorer title={contribution.explorerTitle}>
            <WorkbenchOperationState
              kind="error"
              density="compact"
              title={`Could not load ${contribution.explorerTitle.toLowerCase()}`}
              detail={error.message}
              action={
                <WorkbenchRetryAction
                  label="Reload application"
                  onClick={() => window.location.reload()}
                />
              }
            />
          </LeftExplorer>
        )}
      >
        <Suspense
          fallback={
            <LeftExplorer title={contribution.explorerTitle}>
              <WorkbenchOperationState
                kind="loading"
                density="compact"
                title={`Loading ${contribution.explorerTitle.toLowerCase()}…`}
                skeletonRows={3}
              />
            </LeftExplorer>
          }
        >
          <FeatureExplorer {...explorerProps} />
        </Suspense>
      </SurfaceErrorBoundary>
    );
  }

  return (
    <LeftExplorer title={contribution.explorerTitle} actions={actions} blankMenu={blankMenu}>
      {children ?? (
        <WorkbenchOperationState
          kind="disabled"
          density="compact"
          title="Explorer unavailable"
          detail="This section has no explorer contribution."
        />
      )}
    </LeftExplorer>
  );
};
