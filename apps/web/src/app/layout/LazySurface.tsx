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
  /** Let the enclosing workbench retain its current view during a tab transition. */
  suspense?: boolean;
}

/** Local failure/loading isolation for route chunks and lazy plugin surfaces. */
export const LazySurface = ({
  resetKey,
  loadingTitle = "Loading view…",
  errorTitle = "Could not load this view",
  className,
  children,
  suspense = true,
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
    {suspense ? (
      <Suspense
        fallback={
          <span className="sr-only" role="status">
            {loadingTitle}
          </span>
        }
      >
        {children}
      </Suspense>
    ) : (
      children
    )}
  </SurfaceErrorBoundary>
);
