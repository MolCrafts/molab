import { Menu } from "lucide-react";
import { UserMenu } from "@/app/auth";
import { WorkbenchIconAction } from "@/components/workbench";

interface ContextBarProps {
  /** When set, a hamburger button (mobile only) opens the navigation drawer. */
  onMenuClick?: () => void;
}

export const ContextBar = ({ onMenuClick }: ContextBarProps): JSX.Element => {
  return (
    <header className="flex h-8 flex-none items-center border-b border-border bg-surface-subtle">
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
          <span className="text-label font-medium text-muted-foreground">molab</span>
        </div>

        <div className="flex items-center justify-end gap-1">
          <UserMenu />
        </div>
      </div>
    </header>
  );
};
