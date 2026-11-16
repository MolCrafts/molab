/**
 * Phone chrome (L00, < 768px): an app bar in place of the title bar and the
 * tab row, and a banner in place of the status bar for connection trouble.
 */

import { AlertCircle, Menu, RefreshCw, Search, X } from "lucide-react";
import { type JSX, type Ref, useState } from "react";
import { openCommandPalette } from "@/app/entities/GlobalCommandPalette";
import { WorkbenchIconAction } from "@/components/workbench";

interface MobileAppBarProps {
  title: string;
  context?: string;
  onOpenNavigation: () => void;
  /** Receives the editor-actions slot: the page's primary action sits here. */
  actionsRef: Ref<HTMLDivElement>;
}

export const MobileAppBar = ({
  title,
  context,
  onOpenNavigation,
  actionsRef,
}: MobileAppBarProps): JSX.Element => (
  <header className="flex h-toolbar flex-none items-center gap-1 border-b border-border bg-surface-subtle px-1">
    <WorkbenchIconAction label="Open navigation" size="default" onClick={onOpenNavigation}>
      <Menu className="size-icon-lg" aria-hidden />
    </WorkbenchIconAction>
    <div className="min-w-0 flex-1 px-1">
      <p className="truncate text-body-lg font-medium text-foreground">{title}</p>
      {context ? <p className="truncate text-micro text-muted-foreground">{context}</p> : null}
    </div>
    <WorkbenchIconAction label="Go to" size="default" onClick={() => openCommandPalette("goto")}>
      <Search className="size-icon-lg" aria-hidden />
    </WorkbenchIconAction>
    <div ref={actionsRef} className="flex flex-none items-center gap-1 empty:hidden" />
  </header>
);

interface ConnectionBannerProps {
  message: string;
  actionLabel: string;
  onAction: () => void;
}

/** Shown while the workspace cannot be reached; dismissible until it changes. */
export const ConnectionBanner = ({
  message,
  actionLabel,
  onAction,
}: ConnectionBannerProps): JSX.Element | null => {
  const [dismissed, setDismissed] = useState<string | null>(null);
  if (dismissed === message) return null;
  return (
    <div
      role="status"
      className="mx-4 mt-4 flex flex-none items-center gap-2 rounded-control bg-muted py-1 pr-1 pl-3 text-body"
    >
      <AlertCircle className="size-icon flex-none text-status-warning" aria-hidden />
      <span className="min-w-0 flex-1">{message}</span>
      <WorkbenchIconAction label={actionLabel} size="default" onClick={onAction}>
        <RefreshCw className="size-icon" aria-hidden />
      </WorkbenchIconAction>
      <WorkbenchIconAction label="Dismiss" size="default" onClick={() => setDismissed(message)}>
        <X className="size-icon" aria-hidden />
      </WorkbenchIconAction>
    </div>
  );
};
