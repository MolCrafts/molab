/**
 * The frame every molplot surface has: settings on the left, plot on the right.
 *
 * A chart is never only a chart — it is the plot plus the handful of choices
 * that decide what it is showing (axis, smoothing, how replicas combine). Each
 * surface that grew one of these grew its own copy of the same aside: 240px,
 * a title row, a close button, and a rail with the mirror icon when folded.
 * Two of them drifting apart is a tax on whoever moves between the single-run
 * metrics view and the cross-run comparison, since they are the same act of
 * looking at a curve.
 *
 * So the frame is a component and the surfaces contribute content: `settings`
 * is what the aside holds, `settingsFooter` is what stays pinned under it
 * (counts, sources), and the children are the plot. Open state is
 * controlled-optional: a surface that opens the panel on some other event (a
 * card being selected) drives it, and one that does not just says how it
 * starts.
 */

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { type JSX, type ReactNode, useState } from "react";

import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

export interface ChartWorkbenchProps {
  /** Controls for what the plot shows. */
  settings: ReactNode;
  /** Pinned below the controls — what was read, how much of it. */
  settingsFooter?: ReactNode;
  /** Heading of the settings aside. */
  settingsTitle?: string;
  /** Uncontrolled initial state. Ignored when `open` is given. */
  defaultOpen?: boolean;
  /** Controlled state, for a surface that opens the panel from elsewhere. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** The plot, and anything that belongs to it (a legend, a caption). */
  children: ReactNode;
  className?: string;
}

export const ChartWorkbench = ({
  settings,
  settingsFooter,
  settingsTitle = "Display",
  defaultOpen = false,
  open,
  onOpenChange,
  children,
  className,
}: ChartWorkbenchProps): JSX.Element => {
  const [uncontrolled, setUncontrolled] = useState(defaultOpen);
  const isOpen = open ?? uncontrolled;
  const setOpen = (next: boolean): void => {
    setUncontrolled(next);
    onOpenChange?.(next);
  };

  return (
    <div className={cn("flex min-h-0 flex-1 overflow-hidden bg-background", className)}>
      {isOpen ? (
        <aside className="mol-motion-enter-from-left flex w-60 shrink-0 flex-col gap-4 overflow-y-auto border-r border-border bg-muted/20 px-4 py-4">
          <div className="flex items-center justify-between gap-2">
            <span className="min-w-0 truncate text-body-lg font-medium text-foreground">
              {settingsTitle}
            </span>
            <WorkbenchIconAction label="Hide display settings" onClick={() => setOpen(false)}>
              <PanelLeftClose className="h-4 w-4" />
            </WorkbenchIconAction>
          </div>
          {settings}
          {settingsFooter ? (
            <div className="mt-auto flex flex-col gap-1 border-t border-border pt-3 text-label text-muted-foreground">
              {settingsFooter}
            </div>
          ) : null}
        </aside>
      ) : (
        <div className="flex w-10 shrink-0 flex-col items-center border-r border-border bg-muted/20 pt-3">
          <WorkbenchIconAction label="Show display settings" onClick={() => setOpen(true)}>
            <PanelLeftOpen className="h-4 w-4" />
          </WorkbenchIconAction>
        </div>
      )}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
};
