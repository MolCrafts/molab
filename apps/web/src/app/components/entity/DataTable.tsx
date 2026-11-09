import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@molcrafts/ui";
import type { JSX, ReactNode } from "react";
import { Fragment } from "react";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import { ContextMenuItems } from "@/components/menu/MenuItems";
import { ROW_PADDING_DENSE, TABLE_HEADER } from "./density";

export interface DataTableColumn<T> {
  key: string;
  header: ReactNode;
  width?: string;
  align?: "left" | "right";
  cell: (row: T) => ReactNode;
}

export interface DataTableRowAction<T> {
  id: string;
  label: string;
  shortcut?: string;
  disabled?: boolean;
  destructive?: boolean;
  separatorBefore?: boolean;
  title?: string;
  onSelect: (row: T) => void;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  getRowKey: (row: T) => string;
  /** Open the row (double-click, ↵); without `getRowPreview` a click opens too. */
  onRowActivate?: (row: T) => void;
  /** What a single click / Space / ↑↓ shows in the Preview (L12). */
  getRowPreview?: (row: T) => PreviewTarget | null;
  getRowLabel?: (row: T) => string;
  empty: ReactNode;
  rowClassName?: (row: T) => string;
  rowActions?: (row: T) => DataTableRowAction<T>[];
}

export const DataTable = <T,>({
  columns,
  data,
  getRowKey,
  onRowActivate,
  getRowPreview,
  getRowLabel,
  empty,
  rowClassName,
  rowActions,
}: DataTableProps<T>): JSX.Element => {
  const previewApi = usePreview();
  const renderRow = (row: T): JSX.Element => {
    const actions = rowActions?.(row) ?? [];
    const interactive = Boolean(onRowActivate);
    // Opening the row's page retires the Preview of it.
    const activate = (): void => {
      previewApi.close();
      onRowActivate?.(row);
    };
    const target = getRowPreview?.(row) ?? null;
    const selected = target !== null && previewApi.isPreviewed(target);
    // Single click previews when the row has a target; otherwise it opens.
    const click = (event?: { metaKey: boolean; ctrlKey: boolean }): void => {
      if (target && (event?.metaKey || event?.ctrlKey))
        previewApi.open(target, { background: true });
      else if (target) previewApi.preview(target);
      else activate();
    };
    const rowElement = (
      <TableRow
        tabIndex={interactive ? 0 : undefined}
        aria-label={interactive ? (getRowLabel?.(row) ?? `Open ${getRowKey(row)}`) : undefined}
        aria-selected={target ? selected : undefined}
        className={`group transition-colors hover:bg-interactive/50 focus-visible:bg-interactive/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring ${interactive ? "cursor-pointer" : ""} ${selected ? "bg-accent-muted hover:bg-accent-muted" : ""} ${rowClassName?.(row) ?? ""}`}
        onClick={interactive ? click : undefined}
        onDoubleClick={
          interactive && target
            ? (event) => {
                // A double-click on a control inside the row is that control's.
                const control = (event.target as HTMLElement).closest("button, input, a, label");
                if (control && event.currentTarget.contains(control)) return;
                activate();
              }
            : undefined
        }
        onKeyDown={
          interactive
            ? (event) => {
                if (event.target !== event.currentTarget) return;
                if (target && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
                  // ↑↓ moves through the table and the Preview follows (focus stays here).
                  event.preventDefault();
                  const next =
                    event.key === "ArrowDown"
                      ? event.currentTarget.nextElementSibling
                      : event.currentTarget.previousElementSibling;
                  if (next instanceof HTMLElement) {
                    next.focus();
                    next.click();
                  }
                  return;
                }
                if (event.key === "Enter") {
                  event.preventDefault();
                  activate();
                  return;
                }
                if (event.key === " ") {
                  event.preventDefault();
                  click();
                }
              }
            : undefined
        }
      >
        {columns.map((col) => (
          <TableCell
            key={col.key}
            className={`h-6 px-3 py-0 ${col.align === "right" ? "text-right" : ""}`}
          >
            {col.cell(row)}
          </TableCell>
        ))}
      </TableRow>
    );

    if (actions.length === 0) {
      return <Fragment key={getRowKey(row)}>{rowElement}</Fragment>;
    }

    return (
      <ContextMenu key={getRowKey(row)}>
        <ContextMenuTrigger asChild>{rowElement}</ContextMenuTrigger>
        <ContextMenuContent className="w-52">
          <ContextMenuItems
            actions={actions.map((action) => ({ ...action, onSelect: () => action.onSelect(row) }))}
          />
        </ContextMenuContent>
      </ContextMenu>
    );
  };

  return (
    <div className="flex-1 overflow-auto">
      <Table className="w-full text-left text-body [&_td]:max-w-72 [&_td]:overflow-hidden [&_th]:h-7">
        <TableHeader className={`${TABLE_HEADER} z-10 text-label font-medium`}>
          <TableRow className="hover:bg-transparent">
            {columns.map((col) => (
              <TableHead
                key={col.key}
                className={`${ROW_PADDING_DENSE} ${col.width ?? "w-auto"} ${col.align === "right" ? "text-right" : ""}`}
              >
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody className="divide-y divide-border/50">
          {data.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="py-8">
                {empty}
              </TableCell>
            </TableRow>
          ) : (
            data.map(renderRow)
          )}
        </TableBody>
      </Table>
    </div>
  );
};
