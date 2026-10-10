import { ChevronRight } from "lucide-react";
import type { ComponentType, JSX, MouseEvent, ReactNode } from "react";
import { Fragment, useEffect, useRef, useState } from "react";

export interface TreeClickModifiers {
  shift: boolean;
  meta: boolean;
}

import { EMPTY_COPY, EmptyState } from "@/app/components/entity";
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
  onSelect?: () => void;
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

/** Shared action renderer for tree row menus and panel blank-area menus. */
export const TreeMenuItems = ({ actions }: { actions: TreeNodeAction[] }): JSX.Element => (
  <>
    {actions.map((action) => {
      const ActionIcon = action.icon;
      return (
        <Fragment key={action.id}>
          {action.separatorBefore && <ContextMenuSeparator />}
          <ContextMenuItem
            disabled={action.disabled}
            title={action.title}
            className={
              action.destructive
                ? "text-destructive focus:text-destructive data-[highlighted]:[&_svg]:text-destructive"
                : undefined
            }
            onSelect={() => {
              if (!action.disabled) {
                action.onSelect();
              }
            }}
          >
            {ActionIcon ? <ActionIcon /> : null}
            <span className="min-w-0 flex-1 truncate">{action.label}</span>
            {action.disabled && action.title ? (
              <span className="sr-only">{action.title}</span>
            ) : null}
          </ContextMenuItem>
        </Fragment>
      );
    })}
  </>
);

const INDENT = 14;
/** Always-reserved gutter so sibling expandability never shifts indent. */
const CHEVRON_COL = 24;

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
}: RowProps): JSX.Element => {
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
      className={`group flex h-control-compact min-w-0 flex-1 items-center gap-2 overflow-hidden rounded-hairline px-2 text-left text-body-lg transition-colors ${
        // Soft lavender wash — solid bg-accent is for buttons, too dark on day mode rows.
        isActive
          ? "bg-accent-muted text-accent-muted-foreground"
          : isBagSelected
            ? "bg-muted/60"
            : "hover:bg-muted/40"
      }`}
      onClick={(event) => {
        if (onRowClick) {
          onRowClick(node, event);
          return;
        }
        if (node.onSelect) {
          node.onSelect();
          if (hasChildren && !isExpanded) onToggle(node.id);
        } else if (hasChildren) {
          onToggle(node.id);
        }
      }}
      onContextMenu={() => {
        node.onSelect?.();
      }}
      onPointerEnter={() => node.onPrefetch?.()}
      onFocus={() => node.onPrefetch?.()}
      title={node.hoverTitle ?? node.label}
    >
      {Icon && (
        <Icon
          className={`size-icon-sm flex-none ${node.iconClassName ?? "text-muted-foreground"}`}
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
      onContextMenu={
        actions.length > 0
          ? (event) => {
              // Inner row menu owns this event — do not bubble to panel blank menu.
              event.stopPropagation();
            }
          : undefined
      }
    >
      <div className="flex items-center gap-1" style={{ paddingLeft: `${depth * INDENT}px` }}>
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
              className={`size-icon-sm transition-transform ${isExpanded ? "rotate-90" : ""}`}
            />
          </WorkbenchIconAction>
        ) : (
          <span className="h-6 w-6 flex-none" aria-hidden />
        )}
        {wrappedRow}
      </div>
      {node.children !== undefined && isExpanded && (
        <div>
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
              />
            ))
          )}
        </div>
      )}
    </div>
  );
};

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
    if (node.onSelect) {
      node.onSelect();
      // Opening a folder-like row also shows what is inside it.
      if (node.children !== undefined && !expanded.has(node.id)) toggle(node.id);
    } else if (node.children !== undefined) {
      toggle(node.id);
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
    <div className="space-y-1">
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
        />
      ))}
    </div>
  );
};
