import type { ErrorInfo, ReactNode } from "react";
import { Component } from "react";

interface SurfaceErrorBoundaryProps {
  children: ReactNode;
  fallback: (error: Error) => ReactNode;
  /** Changing the surface identity clears an error captured for the previous surface. */
  resetKey: string;
}

interface SurfaceErrorBoundaryState {
  error: Error | null;
}

/** Keeps a failed lazy feature local to its workbench surface. */
export class SurfaceErrorBoundary extends Component<
  SurfaceErrorBoundaryProps,
  SurfaceErrorBoundaryState
> {
  public state: SurfaceErrorBoundaryState = { error: null };

  public static getDerivedStateFromError(error: Error): SurfaceErrorBoundaryState {
    return { error };
  }

  public componentDidUpdate(previous: SurfaceErrorBoundaryProps): void {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  public componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`Surface "${this.props.resetKey}" failed:`, error, info);
  }

  public render(): ReactNode {
    return this.state.error ? this.props.fallback(this.state.error) : this.props.children;
  }
}
