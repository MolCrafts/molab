import { ChevronRight } from "lucide-react";
import type { ComponentType, JSX, KeyboardEvent, MouseEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

export interface TreeClickModifiers {
  shift: boolean;
  meta: boolean;
}

import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@molcrafts/ui";
import { EMPTY_COPY, EmptyState } from "@/app/components/entity";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import { ContextMenuItems } from "@/components/menu/MenuItems";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

export interface TreeNodeAction {
  id: string;
  label: string;
  /** Shown at the right of the menu item, e.g. "⌥R". */
  shortcut?: string;
  disabled?: boolean;
  destructive?: boolean;
  separatorBefore?: boolean;
  title?: string;
  onSelect: () => void;
}

export interface TreeNode {
  id: string;
  label: string;
  /** Hover tooltip; defaults to `label` (e.g. a long name that the row truncates). */
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
  /** Open the row's page (double-click, ↵). Without `preview`, a click opens too. */
  onSelect?: () => void;
  /** What a single click shows in the Preview (L12). */
  preview?: PreviewTarget;
  /**
   * Intent (hover / keyboard focus): start async work the click will need
   * so the row does not stall after activation.
   */
  onPrefetch?: () => void;
  /**
   * Workspace-qualified bag key. Nodes without it are not modifier-selectable.
   * Distinct from `id`, which is the expand/active row identity.
   */
  selectionKey?: string;
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
   * Parent bumps this after wiping lazy entity caches (manual refresh). Open
   * empty rows re-fire onExpand even when childCount was already 0.
   */
  dataEpoch?: number;
  /** Bag keys currently in the comparison set. Highlight only; does not navigate. */
  selectedIds?: ReadonlySet<string>;
  /**
   * Modifier click on bag-eligible rows. `ids` are `selectionKey`s in visible
   * preorder (shift range already applied). TreeView does not import the bag.
   */
  onModifierSelect?: (ids: readonly string[], modifiers: TreeClickModifiers) => void;
}

/** Visible bag keys in display order — collapsed subtrees and keyless nodes omitted. */
export const visiblePreorder = (
  nodes: readonly TreeNode[],
  expanded: ReadonlySet<string>,
): string[] => {
  const out: string[] = [];
  const walk = (list: readonly TreeNode[]): void => {
    for (const node of list) {
      if (node.selectionKey) out.push(node.selectionKey);
      if (node.children !== undefined && expanded.has(node.id)) walk(node.children);
    }
  };
  walk(nodes);
  return out;
};

/** @deprecated Prefer visiblePreorder. */
export const flattenVisibleIds = visiblePreorder;

/** Tree row and blank-area menus render through the one menu renderer (L13). */
export const TreeMenuItems = ({ actions }: { actions: TreeNodeAction[] }): JSX.Element => (
  <ContextMenuItems actions={actions} />
);

const INDENT = 16;
/** Leading space before the first chevron. */
const ROW_INSET = 8;
/** Always-reserved gutter so sibling expandability never shifts indent. */
const CHEVRON_COL = 16 + ROW_INSET;

interface RowProps {
  node: TreeNode;
  depth: number;
  activeId?: string;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  /** Lazy-load hook — also re-fired when an open node is empty after a refresh. */
  onExpand?: (nodeId: string) => void;
  dataEpoch?: number;
  selectedIds?: ReadonlySet<string>;
  onRowClick?: (node: TreeNode, event: MouseEvent<HTMLButtonElement>) => void;
  /** The one row Tab lands on (roving tabindex); arrows move from there. */
  tabStopId?: string;
}

const TreeRow = ({
  node,
  depth,
  activeId,
  expanded,
  onToggle,
  onExpand,
  dataEpoch = 0,
  selectedIds,
  onRowClick,
  tabStopId,
}: RowProps): JSX.Element => {
  const previewApi = usePreview();
  // Single click (L12): preview when the row has a target, else open; a
  // folder-like row also shows what is inside it.
  const clickNode = (target: TreeNode): void => {
    if (target.preview) previewApi.preview(target.preview);
    else target.onSelect?.();
    if (target.children !== undefined && !expanded.has(target.id)) onToggle(target.id);
  };
  const hasChildren = node.children !== undefined;
  const isExpanded = expanded.has(node.id);
  const isActive = activeId === node.id;
  const isBagSelected = Boolean(node.selectionKey && selectedIds?.has(node.selectionKey));
  const Icon = node.icon;
  const actions = node.actions ?? [];
  const childCount = node.children?.length ?? 0;
  // Parent often passes an inline onExpand; keep a live ref so the empty-heal
  // effect only re-runs when the *node state* changes, not every render.
  const onExpandRef = useRef(onExpand);
  onExpandRef.current = onExpand;

  // Self-heal: TreeView keeps folders open across refresh, but refresh clears
  // lazy entity data. Re-request load while open + empty so we never stick on
  // "Loading…". Parent expand* is idempotent + in-flight guarded.
  // `dataEpoch` is read so a refresh (childCount already 0) still re-fires.
  useEffect(() => {
    if (!isExpanded || node.children === undefined) return;
    if (childCount > 0) return;
    void dataEpoch;
    onExpandRef.current?.(node.id);
  }, [isExpanded, childCount, node.id, node.children, dataEpoch]);

  const rowButton = (
    <WorkbenchAction
      kind="ghost"
      size="content"
      type="button"
      role="treeitem"
      aria-level={depth + 1}
      aria-expanded={hasChildren ? isExpanded : undefined}
      aria-selected={isActive}
      tabIndex={tabStopId === node.id ? 0 : -1}
      // The row's wash lives on the full-width line below; the button stays clear.
      className="group flex h-shell-row min-w-0 flex-1 items-center gap-2 overflow-hidden rounded-none bg-transparent px-1 text-left text-body font-normal text-foreground hover:bg-transparent focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring"
      onClick={(event) => {
        if (onRowClick) {
          onRowClick(node, event);
          return;
        }
        clickNode(node);
      }}
      onDoubleClick={() => {
        // Opening the row's page retires the Preview of it.
        previewApi.close();
        node.onSelect?.();
      }}
      onContextMenu={() => {
        if (node.preview) previewApi.preview(node.preview);
      }}
      onPointerEnter={() => node.onPrefetch?.()}
      onFocus={() => node.onPrefetch?.()}
      title={node.hoverTitle ?? node.label}
    >
      {Icon && (
        <Icon className={`size-icon flex-none ${node.iconClassName ?? "text-muted-foreground"}`} />
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
        <ContextMenuContent className="w-52">
          <TreeMenuItems actions={actions} />
        </ContextMenuContent>
      </ContextMenu>
    ) : (
      rowButton
    );

  return (
    // data-tree-row: panel blank-area menu skips rows that own a context menu.
    // biome-ignore lint/a11y/noStaticElementInteractions: isolates contextmenu, not a click target
    <div
      data-tree-row=""
      data-tree-id={node.id}
      onContextMenu={
        actions.length > 0
          ? (event) => {
              // Inner row menu owns this event — do not bubble to panel blank menu.
              event.stopPropagation();
            }
          : undefined
      }
    >
      <div
        className={cn(
          // VS Code list row: full width, 22px, one selection wash (DS v1.4).
          "flex h-shell-row items-center pr-2",
          isActive ? "bg-accent-muted" : isBagSelected ? "bg-muted" : "hover:bg-interactive",
        )}
        style={{ paddingLeft: `${depth * INDENT + ROW_INSET}px` }}
      >
        {hasChildren ? (
          <WorkbenchIconAction
            label={isExpanded ? "Collapse" : "Expand"}
            className="h-shell-row w-4 flex-none rounded-none text-foreground hover:bg-transparent"
            tabIndex={-1}
            onClick={(event) => {
              event.stopPropagation();
              onToggle(node.id);
            }}
          >
            <ChevronRight
              className={`size-icon transition-transform ${isExpanded ? "rotate-90" : ""}`}
            />
          </WorkbenchIconAction>
        ) : (
          <span className="w-4 flex-none" aria-hidden />
        )}
        {wrappedRow}
      </div>
      {node.children !== undefined && isExpanded && (
        // biome-ignore lint/a11y/useSemanticElements: an ARIA tree's child list is a group, not a fieldset
        <div role="group">
          {node.children.length === 0 && node.emptyChildLabel ? (
            <p
              className="text-label text-muted-foreground"
              style={{ paddingLeft: `${(depth + 1) * INDENT + CHEVRON_COL}px` }}
            >
              {node.emptyChildLabel}
            </p>
          ) : (
            node.children.map((child) => (
              <TreeRow
                key={child.id}
                node={child}
                depth={depth + 1}
                activeId={activeId}
                expanded={expanded}
                onToggle={onToggle}
                onExpand={onExpand}
                dataEpoch={dataEpoch}
                selectedIds={selectedIds}
                onRowClick={onRowClick}
                tabStopId={tabStopId}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
};

/** Whether `id` is on screen: every ancestor of it is expanded. */
const isRendered = (
  nodes: readonly TreeNode[],
  expanded: ReadonlySet<string>,
  id: string,
): boolean =>
  nodes.some(
    (node) =>
      node.id === id ||
      (expanded.has(node.id) &&
        node.children !== undefined &&
        isRendered(node.children, expanded, id)),
  );

export const TreeView = ({
  nodes,
  activeId,
  expandPath,
  emptyTitle,
  emptyDescription,
  emptyIcon,
  onExpand,
  dataEpoch = 0,
  selectedIds,
  onModifierSelect,
}: TreeViewProps): JSX.Element => {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(expandPath ?? []));
  const previewApi = usePreview();
  const onExpandRef = useRef(onExpand);
  onExpandRef.current = onExpand;
  const shiftAnchor = useRef<number | null>(null);
  // Stable key so expandPath array identity churn does not re-fire loads.
  const expandPathKey = expandPath?.join("\0") ?? "";

  useEffect(() => {
    if (!expandPathKey) return;
    const ids = expandPathKey.split("\0").filter(Boolean);
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.add(id);
      return next;
    });
    // Selection-driven expand must also load children (toggle path already does).
    for (const id of ids) {
      onExpandRef.current?.(id);
    }
  }, [expandPathKey]);

  const toggle = (id: string): void => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        onExpandRef.current?.(id);
      }
      return next;
    });
  };

  const handleRowClick = (node: TreeNode, event: MouseEvent<HTMLButtonElement>): void => {
    const modifiers: TreeClickModifiers = {
      shift: event.shiftKey,
      meta: event.metaKey || event.ctrlKey,
    };
    if (onModifierSelect && node.selectionKey && (modifiers.shift || modifiers.meta)) {
      event.preventDefault();
      const ordered = visiblePreorder(nodes, expanded);
      const index = ordered.indexOf(node.selectionKey);
      if (index < 0) return;
      if (modifiers.shift && shiftAnchor.current !== null) {
        const [lo, hi] =
          shiftAnchor.current <= index
            ? [shiftAnchor.current, index]
            : [index, shiftAnchor.current];
        onModifierSelect(ordered.slice(lo, hi + 1), modifiers);
        return;
      }
      shiftAnchor.current = index;
      onModifierSelect([node.selectionKey], modifiers);
      return;
    }
    if (node.selectionKey) {
      const ordered = visiblePreorder(nodes, expanded);
      shiftAnchor.current = ordered.indexOf(node.selectionKey);
    }
    if (node.preview) previewApi.preview(node.preview);
    else node.onSelect?.();
    // A folder-like row also shows what is inside it.
    if (node.children !== undefined && !expanded.has(node.id)) toggle(node.id);
  };

  const tabStopId =
    activeId && isRendered(nodes, expanded, activeId) ? activeId : (nodes[0]?.id ?? undefined);

  // ARIA tree keys (L00): ↑↓ Home End move, → opens / enters, ← closes / climbs.
  const onTreeKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const items = [...event.currentTarget.querySelectorAll<HTMLElement>('[role="treeitem"]')];
    const current = (event.target as HTMLElement).closest<HTMLElement>('[role="treeitem"]');
    const index = current ? items.indexOf(current) : -1;
    if (!current || index < 0) return;
    const id = current.closest<HTMLElement>("[data-tree-id]")?.dataset.treeId;
    const level = Number(current.getAttribute("aria-level") ?? "1");
    const state = current.getAttribute("aria-expanded");
    const move = (target: number): void => {
      event.preventDefault();
      items[Math.max(0, Math.min(items.length - 1, target))]?.focus();
    };
    switch (event.key) {
      case "Enter":
        // ↵ opens the page; a click (or Space) only previews (L12).
        event.preventDefault();
        current.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
        return;
      case "ArrowDown":
        move(index + 1);
        return;
      case "ArrowUp":
        move(index - 1);
        return;
      case "Home":
        move(0);
        return;
      case "End":
        move(items.length - 1);
        return;
      case "ArrowRight":
        event.preventDefault();
        if (state === "false" && id) toggle(id);
        else if (
          state === "true" &&
          Number(items[index + 1]?.getAttribute("aria-level")) === level + 1
        ) {
          move(index + 1);
        }
        return;
      case "ArrowLeft": {
        event.preventDefault();
        if (state === "true" && id) {
          toggle(id);
          return;
        }
        for (let i = index - 1; i >= 0; i -= 1) {
          if (Number(items[i]?.getAttribute("aria-level")) === level - 1) {
            move(i);
            return;
          }
        }
        return;
      }
    }
  };

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

  return (
    <div role="tree" aria-label="Explorer" onKeyDown={onTreeKeyDown}>
      {nodes.map((node) => (
        <TreeRow
          key={node.id}
          node={node}
          depth={0}
          activeId={activeId}
          expanded={expanded}
          onToggle={toggle}
          onExpand={onExpand}
          dataEpoch={dataEpoch}
          selectedIds={selectedIds}
          onRowClick={onModifierSelect ? handleRowClick : undefined}
          tabStopId={tabStopId}
        />
      ))}
    </div>
  );
};
