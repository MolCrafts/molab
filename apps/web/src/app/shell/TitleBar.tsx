/**
 * Title bar (L00): wordmark · command centre · layout toggles. 35px, the only
 * band above the work; the account lives in the activity bar.
 */

import { Kbd } from "@molcrafts/ui";
import { Layers, PanelBottom, PanelLeft, Search } from "lucide-react";
import type { JSX } from "react";
import { openCommandPalette } from "@/app/entities/GlobalCommandPalette";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import { SHORTCUTS } from "./keys";

interface TitleBarProps {
  workspaceLabel: string;
  sideBarVisible: boolean;
  onToggleSideBar: () => void;
  /** Omitted when no plugin contributes a bottom panel. */
  panelVisible?: boolean;
  onTogglePanel?: () => void;
}

export const TitleBar = ({
  workspaceLabel,
  sideBarVisible,
  onToggleSideBar,
  panelVisible,
  onTogglePanel,
}: TitleBarProps): JSX.Element => (
  <header
    className="relative flex h-shell-titlebar flex-none items-center border-b border-border bg-surface-subtle px-2"
    data-shell-region="titlebar"
  >
    <div className="flex min-w-0 items-center gap-2 pl-1">
      <Layers className="size-icon flex-none text-accent" aria-hidden />
      <span className="text-label text-muted-foreground">molab</span>
    </div>

    {/* Centred on the window, not on what is left of it. */}
    <div className="pointer-events-none absolute inset-x-0 flex justify-center px-48">
      <button
        type="button"
        className={cn(
          "pointer-events-auto flex h-shell-action w-full max-w-md min-w-0 items-center justify-center gap-2",
          "rounded-control border border-border bg-background px-2 text-label text-muted-foreground",
          "outline-none hover:bg-interactive focus-visible:ring-2 focus-visible:ring-ring",
        )}
        aria-label={`Go to in ${workspaceLabel}`}
        aria-keyshortcuts="Meta+K Control+K"
        onClick={() => openCommandPalette("goto")}
      >
        <Search className="size-icon-sm flex-none" aria-hidden />
        <span className="truncate">{workspaceLabel}</span>
        <Kbd className="flex-none">{SHORTCUTS.goTo()}</Kbd>
      </button>
    </div>

    <div className="ml-auto flex items-center gap-hairline">
      <WorkbenchIconAction
        size="shell"
        label="Toggle Side Bar"
        shortcut={SHORTCUTS.sideBar()}
        aria-pressed={sideBarVisible}
        onClick={onToggleSideBar}
      >
        <PanelLeft aria-hidden />
      </WorkbenchIconAction>
      {onTogglePanel ? (
        <WorkbenchIconAction
          size="shell"
          label="Toggle Panel"
          shortcut={SHORTCUTS.panel()}
          aria-pressed={Boolean(panelVisible)}
          onClick={onTogglePanel}
        >
          <PanelBottom aria-hidden />
        </WorkbenchIconAction>
      ) : null}
    </div>
  </header>
);
