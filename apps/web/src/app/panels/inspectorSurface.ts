import type { ReactNode } from "react";

export interface InspectorSurfaceRenderProps {
  className?: string;
}

/**
 * A contextual detail surface registered by the feature that owns the current
 * work surface. The shell controls placement and visibility without importing
 * feature-specific inspector components or data types.
 */
export interface InspectorSurfaceRegistration {
  /** Stable identity used to open the inspector when the inspected item changes. */
  id: string;
  render: (props: InspectorSurfaceRenderProps) => ReactNode;
}
