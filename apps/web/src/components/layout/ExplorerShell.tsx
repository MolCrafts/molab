/**
 * Domain-free explorer shell: icon rail + titled, scrollable explorer column.
 *
 * Products own navigation descriptors and explorer content. This block owns
 * only shared chrome, accessibility, and layout behavior.
 */
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
  ScrollArea,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@molcrafts/ui";
import type { ButtonHTMLAttributes, ComponentType, JSX, ReactNode, SVGProps } from "react";
import { cn } from "@/lib/utils";

export interface LeftIconRailItem {
  id: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Add a quiet visual group boundary before this item. */
  separatorBefore?: boolean;
  /** Hover / focus intent: start loading this section before click. */
  onIntent?: () => void;
}

export interface LeftIconRailProps {
  items: LeftIconRailItem[];
  activeId: string;
  onSelect: (id: string) => void;
  /** Optional item pinned to the bottom of the rail. */
  footer?: LeftIconRailItem | null;
  /** Controls above the footer item (the account menu). */
  footerSlot?: ReactNode;
  ariaLabel?: string;
  className?: string;
}

/** One activity-bar cell: 48px square, 24px glyph, 2px accent bar when active. */
export const ActivityBarButton = ({
  label,
  active = false,
  icon: Icon,
  className,
  ...rest
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  label: string;
  active?: boolean;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}): JSX.Element => (
  <Tooltip delayDuration={500}>
    <TooltipTrigger asChild>
      <button
        type="button"
        aria-label={label}
        className={cn(
          "relative flex size-12 flex-none items-center justify-center text-muted-foreground outline-none",
          "hover:text-foreground focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
          "before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-transparent",
          active && "text-foreground before:bg-accent",
          className,
        )}
        {...rest}
      >
        <Icon className="size-6" aria-hidden />
      </button>
    </TooltipTrigger>
    <TooltipContent
      side="right"
      sideOffset={2}
      className="rounded-hairline border border-border px-2 py-1 text-label"
    >
      {label}
    </TooltipContent>
  </Tooltip>
);

/** VS Code activity bar: section switcher, account and settings at the foot. */
export const LeftIconRail = ({
  items,
  activeId,
  onSelect,
  footer = null,
  footerSlot,
  ariaLabel = "Activity bar",
  className,
}: LeftIconRailProps): JSX.Element => {
  const itemButton = (item: LeftIconRailItem): JSX.Element => (
    <ActivityBarButton
      key={item.id}
      label={item.label}
      icon={item.icon}
      active={activeId === item.id}
      aria-pressed={activeId === item.id}
      onClick={() => onSelect(item.id)}
      onPointerEnter={() => item.onIntent?.()}
      onFocus={() => item.onIntent?.()}
    />
  );

  return (
    <nav
      className={cn(
        "flex w-12 shrink-0 flex-col border-r border-border bg-surface-subtle",
        className,
      )}
      aria-label={ariaLabel}
      data-shell-region="activitybar"
    >
      {items.map((item) => (
        <div key={item.id} className="flex flex-col">
          {item.separatorBefore ? <div className="mx-3 my-1 h-px bg-border" aria-hidden /> : null}
          {itemButton(item)}
        </div>
      ))}
      <div className="mt-auto flex flex-col">
        {footerSlot}
        {footer ? itemButton(footer) : null}
      </div>
    </nav>
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
        // h-full: a resizable panel wraps its child in a block, so flex-1 alone
        // lets the column grow to its content and the whole column (header
        // included) scrolls instead of the body.
        "flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-surface-subtle outline-none",
        className,
      )}
    >
      <header className="flex min-h-shell-row shrink-0 items-center pr-1 pl-3">
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
          <h2 className="min-w-0 truncate text-micro font-semibold uppercase tracking-wide text-foreground">
            {title}
          </h2>
          {actions ? (
            <div className="flex shrink-0 items-center gap-hairline [&_button]:size-shell-action [&_button]:rounded-action">
              {actions}
            </div>
          ) : null}
        </div>
        {toolbar ? <div className="space-y-2">{toolbar}</div> : null}
      </header>

      {/* Radix wraps the body in display:table, which sizes rows to their
          content and defeats truncate; block keeps rows at the column width. */}
      <ScrollArea className="min-h-0 flex-1 [&_[data-radix-scroll-area-viewport]>div]:!block">
        <div className={cn("min-h-full", bodyClassName)}>{children}</div>
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

/** Dock height when nothing is persisted — about six rows plus its header.
 *  Min is header + one two-line item; 60px clips the bag under overflow-hidden. */
const DOCK_SIZE = { default: "160px", min: "88px", max: "70%" };

export interface ExplorerDockProps {
  /** The explorer column; takes whatever height the dock leaves it. */
  children: ReactNode;
  /** The surface pinned below it, resizable and persisted across sessions. */
  dock: ReactNode;
  /**
   * Panel-group id. Products namespace it so two docks in one app — or two
   * apps in one browser origin — do not share a persisted height.
   */
  id?: string;
  /** Storage key for the persisted split. Defaults to `${id}.size`. */
  autoSaveId?: string;
  /**
   * Fold the dock to its header (`collapsedSize`) without unmounting the
   * explorer above it; the persisted split is left alone while folded.
   */
  collapsed?: boolean;
  collapsedSize?: string;
}

/**
 * An explorer column with a second surface docked beneath it.
 *
 * A surface that has to outlive the section it was opened from cannot live
 * inside one explorer's scroller — it has to be part of the panel. Its height
 * is the user's: how much of the panel a staging area deserves depends on
 * what they are staging, so the split is draggable and remembered.
 */
export const ExplorerDock = ({
  children,
  dock,
  id = "explorer-dock",
  autoSaveId,
  collapsed = false,
  collapsedSize = "23px",
}: ExplorerDockProps): JSX.Element => (
  <ResizablePanelGroup
    id={id}
    direction="vertical"
    autoSaveId={collapsed ? undefined : (autoSaveId ?? `${id}.size`)}
    autoSavePanelIds={["explorer", "dock"]}
    className="min-h-0 min-w-0 flex-1"
  >
    {/* No defaultSize: react-resizable-panels v4 does not parse calc(), so
        the explorer takes whatever the dock leaves. */}
    <ResizablePanel id="explorer" minSize="88px">
      {children}
    </ResizablePanel>
    <ResizableHandle className={HORIZONTAL_HANDLE} disabled={collapsed} />
    <ResizablePanel
      id="dock"
      defaultSize={collapsed ? collapsedSize : DOCK_SIZE.default}
      minSize={collapsed ? collapsedSize : DOCK_SIZE.min}
      maxSize={collapsed ? collapsedSize : DOCK_SIZE.max}
    >
      {dock}
    </ResizablePanel>
  </ResizablePanelGroup>
);
