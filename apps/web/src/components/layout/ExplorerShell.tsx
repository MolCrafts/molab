/**
 * Domain-free explorer shell: icon rail + titled, scrollable explorer column.
 *
 * Products own navigation descriptors and explorer content. This block owns
 * only shared chrome, accessibility, and layout behavior.
 */
import type { ComponentType, JSX, ReactNode, SVGProps } from "react";
import { Button } from "@/components/ui/button";
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@/components/ui/context-menu";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface LeftIconRailItem {
  id: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Add a quiet visual group boundary before this item. */
  separatorBefore?: boolean;
}

export interface LeftIconRailProps {
  items: LeftIconRailItem[];
  activeId: string;
  onSelect: (id: string) => void;
  /** Optional item pinned to the bottom of the rail. */
  footer?: LeftIconRailItem | null;
  ariaLabel?: string;
  className?: string;
}

export const LeftIconRail = ({
  items,
  activeId,
  onSelect,
  footer = null,
  ariaLabel = "Explorer views",
  className,
}: LeftIconRailProps): JSX.Element => {
  const itemButton = (item: LeftIconRailItem): JSX.Element => {
    const Icon = item.icon;
    return (
      <Tooltip key={item.id}>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={item.label}
            aria-pressed={activeId === item.id}
            title={item.label}
            className={cn(
              "relative size-8 rounded-control text-muted-foreground",
              "after:absolute after:-left-2 after:inset-y-1 after:w-0.5 after:rounded-full after:bg-transparent",
              activeId === item.id &&
                "bg-background text-foreground after:bg-accent hover:bg-background",
            )}
            onClick={() => onSelect(item.id)}
          >
            <Icon className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right">{item.label}</TooltipContent>
      </Tooltip>
    );
  };

  return (
    <TooltipProvider>
      <nav
        className={cn(
          "flex w-12 shrink-0 flex-col items-center gap-1 border-r border-border bg-muted py-3",
          className,
        )}
        aria-label={ariaLabel}
      >
        {items.map((item) => (
          <div
            key={item.id}
            className={cn(
              "flex flex-col items-center",
              item.separatorBefore && "mt-1 border-t border-border pt-2",
            )}
          >
            {itemButton(item)}
          </div>
        ))}
        {footer ? <div className="mt-auto">{itemButton(footer)}</div> : null}
      </nav>
    </TooltipProvider>
  );
};
export interface LeftExplorerProps {
  title: string;
  actions?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
  /** Context-menu items shown when the explorer's blank area is opened. */
  blankMenu?: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export const LeftExplorer = ({
  title,
  actions,
  toolbar,
  children,
  blankMenu,
  className,
  bodyClassName,
}: LeftExplorerProps): JSX.Element => {
  const column = (
    <div
      className={cn(
        "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background outline-none",
        className,
      )}
    >
      <header className="flex h-[35px] shrink-0 items-center border-b border-border px-2">
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
          <h2 className="min-w-0 truncate text-label font-semibold uppercase tracking-wide text-muted-foreground">
            {title}
          </h2>
          {actions ? <div className="flex shrink-0 items-center gap-0.5">{actions}</div> : null}
        </div>
        {toolbar ? <div className="space-y-1.5">{toolbar}</div> : null}
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <div className={cn("min-h-full px-2 py-1.5", bodyClassName)}>{children}</div>
      </ScrollArea>
    </div>
  );

  if (!blankMenu) return column;

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{column}</ContextMenuTrigger>
      <ContextMenuContent className="w-52">{blankMenu}</ContextMenuContent>
    </ContextMenu>
  );
};

/**
 * A horizontal separator out of the vertical-by-default handle: the shadcn
 * wrapper styles the common case (a column divider), and `cn` lets the later
 * class win for the row divider this group needs.
 */
const HORIZONTAL_HANDLE =
  "h-px w-full after:inset-x-0 after:left-0 after:top-1/2 after:bottom-auto after:h-1 after:w-full after:translate-x-0 after:-translate-y-1/2 hover:bg-accent/60";

/** Dock height when nothing is persisted — about six rows plus its header. */
const DOCK_SIZE = { default: "200px", min: "60px", max: "70%" };

export interface ExplorerDockProps {
  /** The explorer column; takes whatever height the dock leaves it. */
  children: ReactNode;
  /** The surface pinned below it, resizable and persisted across sessions. */
  dock: ReactNode;
}

/**
 * An explorer column with a second surface docked beneath it.
 *
 * A surface that has to outlive the section it was opened from cannot live
 * inside one explorer's scroller — it has to be part of the panel. Its height
 * is the user's: how much of the panel a staging area deserves depends on
 * what they are staging, so the split is draggable and remembered.
 */
export const ExplorerDock = ({ children, dock }: ExplorerDockProps): JSX.Element => (
  <ResizablePanelGroup
    id="molexp-explorer-dock"
    direction="vertical"
    autoSaveId="molexp.explorerDock"
    autoSavePanelIds={["explorer", "dock"]}
    className="min-h-0 min-w-0 flex-1"
  >
    <ResizablePanel id="explorer" defaultSize="calc(100% - 200px)" minSize="88px">
      {children}
    </ResizablePanel>
    <ResizableHandle className={HORIZONTAL_HANDLE} />
    <ResizablePanel
      id="dock"
      defaultSize={DOCK_SIZE.default}
      minSize={DOCK_SIZE.min}
      maxSize={DOCK_SIZE.max}
    >
      {dock}
    </ResizablePanel>
  </ResizablePanelGroup>
);
