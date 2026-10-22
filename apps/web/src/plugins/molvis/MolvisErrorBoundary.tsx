import { Atom } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { EmptyState } from "@/app/components/entity";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Keeps a molvis-core / WebGL throw from taking down the whole app. */
export class MolvisErrorBoundary extends Component<Props, State> {
  public state: State = { error: null };

  public static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  public componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("molvis viewer failed:", error, info);
  }

  public componentDidUpdate(prev: Props): void {
    if (prev.children !== this.props.children && this.state.error) {
      this.setState({ error: null });
    }
  }

  public render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="flex h-full items-center justify-center p-6">
          <EmptyState
            icon={<Atom className="h-6 w-6" />}
            title="Cannot open in MolVis"
            description={this.state.error.message}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
