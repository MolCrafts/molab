import { type ReactNode, Suspense } from "react";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import { SurfaceErrorBoundary } from "./SurfaceErrorBoundary";

interface LazySurfaceProps {
  resetKey: string;
  loadingTitle?: string;
  errorTitle?: string;
  className?: string;
  children: ReactNode;
}

/** Local failure/loading isolation for route chunks and lazy plugin surfaces. */
export const LazySurface = ({
  resetKey,
  loadingTitle = "Loading view…",
  errorTitle = "Could not load this view",
  className,
  children,
}: LazySurfaceProps): JSX.Element => (
  <SurfaceErrorBoundary
    resetKey={resetKey}
    fallback={(error) => (
      <div className={cn("flex h-full items-center justify-center p-6", className)}>
        <WorkbenchOperationState
          kind="error"
          title={errorTitle}
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
        <div className={cn("flex h-full items-center justify-center p-6", className)}>
          <WorkbenchOperationState kind="loading" title={loadingTitle} />
        </div>
      }
    >
      {children}
    </Suspense>
  </SurfaceErrorBoundary>
);
