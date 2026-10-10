import { Menu } from "lucide-react";
import { UserMenu } from "@/app/auth";
import { WorkbenchIconAction } from "@/components/workbench";

interface ContextBarProps {
  /** When set, a hamburger button (mobile only) opens the navigation drawer. */
  onMenuClick?: () => void;
}

export const ContextBar = ({ onMenuClick }: ContextBarProps): JSX.Element => {
  return (
    <header className="flex h-toolbar-compact flex-none items-center border-b border-border bg-surface-subtle">
      <div className="flex h-full w-full items-center justify-between gap-2 px-3">
        <div className="flex min-w-0 items-center gap-2">
          {onMenuClick && (
            <WorkbenchIconAction
              label="Open navigation"
              size="default"
              className="flex-none md:hidden"
              onClick={onMenuClick}
            >
              <Menu className="size-icon" />
            </WorkbenchIconAction>
          )}
          {/* Product identity once, top-left. Keep the mascot out of dense chrome. */}
          <span className="flex min-w-0 items-center gap-2">
            <span
              aria-hidden="true"
              className="flex size-6 flex-none items-center justify-center rounded-control bg-status-completed-soft text-micro font-semibold text-status-completed-foreground"
            >
              M
            </span>
            <span className="text-title font-semibold tracking-tight text-foreground">molab</span>
          </span>
        </div>

        <div className="flex items-center justify-end gap-1">
          <UserMenu />
        </div>
      </div>
    </header>
  );
};
