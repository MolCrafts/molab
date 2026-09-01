/**
 * Domain-free explorer shell: icon rail + titled, scrollable explorer column.
 *
 * Products own navigation descriptors and explorer content. This block owns
 * only shared chrome, accessibility, and layout behavior.
 */
import type { ComponentType, JSX, ReactNode, SVGProps } from "react";
import { Button } from "@/components/ui/button";
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@/components/ui/context-menu";
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
