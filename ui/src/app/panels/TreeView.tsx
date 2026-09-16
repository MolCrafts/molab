import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronRight } from "lucide-react";
import type { ComponentType, JSX, ReactNode } from "react";
import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { EMPTY_COPY, EmptyState } from "@/app/components/entity";
import { type FlatTreeRow, flattenVisible, indexOfNode } from "@/app/panels/treeFlatten";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";

export interface TreeNodeAction {
  id: string;
  label: string;
  icon?: ComponentType<{ className?: string }>;
  disabled?: boolean;
  destructive?: boolean;
  separatorBefore?: boolean;
  title?: string;
  onSelect: () => void;
}

export interface TreeNode {
  id: string;
  label: string;
  /** Hover tooltip; defaults to `label` (e.g. an agent task's full goal). */
  hoverTitle?: string;
  labelClassName?: string;
  icon?: ComponentType<{ className?: string }>;
  iconClassName?: string;
  leadingAccessory?: ReactNode;
  right?: ReactNode;
  meta?: ReactNode;
  children?: TreeNode[];
  emptyChildLabel?: string;
  actions?: TreeNodeAction[];
  onSelect?: () => void;
}

interface TreeViewProps {
  nodes: TreeNode[];
  activeId?: string;
  expandPath?: string[];
  emptyTitle?: string;
  emptyDescription?: string;
  emptyIcon?: ReactNode;
  /** Fired when a node is expanded (not collapsed). Used for lazy WorkspaceFs.listdir. */
  onExpand?: (nodeId: string) => void;
  /**
   * Fired after a short sustained hover/focus on a row, so the panel can warm
   * that node's query before the click. Cancelled on leave/blur, so a pointer
   * sweeping down the tree issues nothing.
   */
  onHoverIntent?: (nodeId: string) => void;
}

/** Delay before a hover counts as intent (matches `usePrefetchOnIntent`). */
const HOVER_INTENT_MS = 120;

const INDENT = 14;

/** Row height (`h-control-compact`, 28px) — the virtualizer's size estimate. */
const ROW_PX = 28;
/** The childless-parent placeholder is a text line, not a control row. */
const EMPTY_ROW_PX = 20;
/**
 * Below this many visible rows the tree renders every row.
 *
 * Windowing costs a scroll container, absolute positioning and a measure pass;
 * it also drops off-screen rows out of the DOM, which breaks Tab traversal and
 * browser find-in-page. Small trees (most views) are better off without it, so
 * the cost is paid only where it buys something — an experiment holding
 * thousands of runs, or a large knowledge base.
 */
const VIRTUALIZE_THRESHOLD = 100;

/** Nearest scrollable ancestor — the element the virtualizer must observe. */
const findScrollParent = (start: HTMLElement | null): HTMLElement | null => {
  let current = start?.parentElement ?? null;
  while (current) {
    const overflowY = getComputedStyle(current).overflowY;
    if (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") {
      return current;
    }
    current = current.parentElement;
  }
  return null;
};

interface RowProps {
  node: TreeNode;
  depth: number;
  /** True if any sibling at this level has children. Drives the chevron-column reservation. */
  reserveChevron: boolean;
  activeId?: string;
  isExpanded: boolean;
  onToggle: (id: string) => void;
  onHoverIntent?: (id: string) => void;
}

const TreeRow = ({
  node,
  depth,
  reserveChevron,
  activeId,
  isExpanded,
  onToggle,
  onHoverIntent,
}: RowProps): JSX.Element => {
  const intentTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelIntent = (): void => {
    if (intentTimer.current !== null) {
      clearTimeout(intentTimer.current);
      intentTimer.current = null;
    }
  };
  const armIntent = (): void => {
    if (!onHoverIntent || intentTimer.current !== null) return;
    intentTimer.current = setTimeout(() => {
      intentTimer.current = null;
      onHoverIntent(node.id);
    }, HOVER_INTENT_MS);
  };
  // Unmount-only cleanup: reads the ref directly so it needs no dependency
  // (depending on `cancelIntent` would re-run — and cancel — every render).
  useEffect(
    () => () => {
      if (intentTimer.current !== null) clearTimeout(intentTimer.current);
    },
    [],
  );

  const hasChildren = node.children !== undefined;
  const isActive = activeId === node.id;
  const Icon = node.icon;
  const actions = node.actions ?? [];

  const rowButton = (
    <WorkbenchAction
      kind="ghost"
      size="content"
      type="button"
      className={`group flex h-control-compact min-w-0 flex-1 items-center gap-2 overflow-hidden rounded-control px-2 text-left text-body-lg transition-colors ${
        // Soft lavender wash — solid bg-accent is for buttons, too dark on day mode rows.
        isActive ? "bg-accent-muted text-accent-muted-foreground" : "hover:bg-muted/40"
      }`}
      onClick={() => {
        if (node.onSelect) {
          node.onSelect();
        } else if (hasChildren) {
          onToggle(node.id);
        }
      }}
      onContextMenu={() => {
        node.onSelect?.();
      }}
      onMouseEnter={armIntent}
      onFocus={armIntent}
      onMouseLeave={cancelIntent}
      onBlur={cancelIntent}
      title={node.hoverTitle ?? node.label}
    >
      {Icon && (
        <Icon
          className={`h-3.5 w-3.5 flex-none ${node.iconClassName ?? "text-muted-foreground"}`}
        />
      )}
      {node.leadingAccessory && <span className="flex-none">{node.leadingAccessory}</span>}
      <span className={`min-w-0 flex-1 truncate ${node.labelClassName ?? ""}`}>{node.label}</span>
      {node.right && <span className="flex-none">{node.right}</span>}
      {node.meta !== undefined && node.meta !== null && (
        <span className="flex-none font-mono text-micro text-muted-foreground">{node.meta}</span>
      )}
    </WorkbenchAction>
  );

  const wrappedRow =
    actions.length > 0 ? (
      <ContextMenu>
        <ContextMenuTrigger asChild>{rowButton}</ContextMenuTrigger>
        <ContextMenuContent>
          {actions.map((action) => {
            const ActionIcon = action.icon;
            return (
              <Fragment key={action.id}>
                {action.separatorBefore && <ContextMenuSeparator />}
                <ContextMenuItem
                  disabled={action.disabled}
                  title={action.title}
                  className={
                    action.destructive ? "text-destructive focus:text-destructive" : undefined
                  }
                  onSelect={() => {
                    if (!action.disabled) {
                      action.onSelect();
                    }
                  }}
                >
                  {ActionIcon && <ActionIcon className="mr-2 h-3.5 w-3.5" />}
                  <span className="truncate">{action.label}</span>
                </ContextMenuItem>
              </Fragment>
            );
          })}
        </ContextMenuContent>
      </ContextMenu>
    ) : (
      rowButton
    );

  // One flat row: the subtree is spliced in by `flattenVisible`, not nested
  // here, so every visible line is a sibling the virtualizer can address.
  return (
    <div
      className="flex h-control-compact items-center gap-1"
      style={{ paddingLeft: `${depth * INDENT}px` }}
    >
      {hasChildren ? (
        <WorkbenchIconAction
          label={isExpanded ? "Collapse" : "Expand"}
          className="size-6 flex-none text-muted-foreground"
          onClick={(event) => {
            event.stopPropagation();
            onToggle(node.id);
          }}
        >
          <ChevronRight
            className={`h-3.5 w-3.5 transition-transform ${isExpanded ? "rotate-90" : ""}`}
          />
        </WorkbenchIconAction>
      ) : reserveChevron ? (
        <span className="h-6 w-6 flex-none" />
      ) : null}
      {wrappedRow}
    </div>
  );
};

/** The "expanded, but nothing inside" placeholder line. */
const TreeEmptyRow = ({ row }: { row: FlatTreeRow }): JSX.Element => (
  <p
    className="text-label text-muted-foreground"
    style={{ paddingLeft: `${row.depth * INDENT + 8}px` }}
  >
    {row.node.emptyChildLabel}
  </p>
);

export const TreeView = ({
  nodes,
  activeId,
  expandPath,
  emptyTitle,
  emptyDescription,
  emptyIcon,
  onExpand,
  onHoverIntent,
}: TreeViewProps): JSX.Element => {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(expandPath ?? []));

  useEffect(() => {
    if (!expandPath || expandPath.length === 0) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const id of expandPath) next.add(id);
      return next;
    });
  }, [expandPath]);

  const toggle = (id: string): void => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        onExpand?.(id);
      }
      return next;
    });
  };

  // The render list: every visible line, in order. Recomputed only when the
  // forest or the expansion set changes, so scrolling never re-walks the tree.
  const rows = useMemo(() => flattenVisible(nodes, expanded), [nodes, expanded]);

  // The virtualizer needs the scrolling ancestor, which this component does not
  // own — callers drop the tree inside their own ScrollArea.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollEl, setScrollEl] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    setScrollEl(findScrollParent(containerRef.current));
  }, []);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollEl,
    estimateSize: (index) => (rows[index]?.kind === "empty" ? EMPTY_ROW_PX : ROW_PX),
    getItemKey: (index) => rows[index]?.key ?? index,
    overscan: 12,
  });

  // Windowing only pays off on a long list, and only once we know what scrolls.
  const virtualize = scrollEl !== null && rows.length >= VIRTUALIZE_THRESHOLD;

  // Keep the selected row reachable when it is scrolled out of the window.
  // Guarded by the id so an unrelated refetch never yanks the user's scroll.
  const scrolledFor = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!virtualize || activeId === undefined || scrolledFor.current === activeId) return;
    const index = indexOfNode(rows, activeId);
    if (index < 0) return;
    scrolledFor.current = activeId;
    virtualizer.scrollToIndex(index, { align: "auto" });
  }, [activeId, rows, virtualize, virtualizer]);

  if (nodes.length === 0) {
    return (
      <EmptyState
        title={emptyTitle ?? EMPTY_COPY.entries.title}
        description={emptyDescription}
        icon={emptyIcon}
        density="compact"
      />
    );
  }

  const renderRow = (row: FlatTreeRow): JSX.Element =>
    row.kind === "empty" ? (
      <TreeEmptyRow row={row} />
    ) : (
      <TreeRow
        node={row.node}
        depth={row.depth}
        reserveChevron={row.reserveChevron}
        activeId={activeId}
        isExpanded={expanded.has(row.node.id)}
        onToggle={toggle}
        onHoverIntent={onHoverIntent}
      />
    );

  return (
    <div ref={containerRef}>
      {virtualize ? (
        <div className="relative w-full" style={{ height: `${virtualizer.getTotalSize()}px` }}>
          {virtualizer.getVirtualItems().map((item) => {
            const row = rows[item.index];
            if (!row) return null;
            return (
              <div
                key={row.key}
                data-index={item.index}
                ref={virtualizer.measureElement}
                className="absolute top-0 left-0 w-full"
                style={{ transform: `translateY(${item.start}px)` }}
              >
                {renderRow(row)}
              </div>
            );
          })}
        </div>
      ) : (
        rows.map((row) => <Fragment key={row.key}>{renderRow(row)}</Fragment>)
      )}
    </div>
  );
};
