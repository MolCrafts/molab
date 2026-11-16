/**
 * Menu items (L13; retrofit R5 — icon OR text): every item is a verb and its
 * key at the right, words only, as VS Code menus. Separators group by what they
 * act on; a destructive item is red and carries "…" when it asks first. One
 * renderer for tree, table and explorer context menus.
 */

import { ContextMenuItem, ContextMenuSeparator, ContextMenuShortcut } from "@molcrafts/ui";
import { Fragment, type JSX } from "react";
import { cn } from "@/lib/utils";

export interface MenuAction {
  id: string;
  label: string;
  /** Shown at the right, e.g. "⌥R". */
  shortcut?: string;
  disabled?: boolean;
  destructive?: boolean;
  separatorBefore?: boolean;
  /** Why it is disabled, for hover and assistive tech. */
  title?: string;
  onSelect: () => void;
}

export const ContextMenuItems = ({ actions }: { actions: readonly MenuAction[] }): JSX.Element => {
  return (
    <>
      {actions.map((action) => {
        return (
          <Fragment key={action.id}>
            {action.separatorBefore ? <ContextMenuSeparator /> : null}
            <ContextMenuItem
              disabled={action.disabled}
              title={action.title}
              className={cn(
                "gap-2",
                action.destructive &&
                  "text-destructive focus:text-destructive data-[highlighted]:text-destructive",
              )}
              onSelect={() => {
                if (!action.disabled) action.onSelect();
              }}
            >
              <span className="min-w-0 flex-1 truncate">{action.label}</span>
              {action.shortcut ? (
                <ContextMenuShortcut>{action.shortcut}</ContextMenuShortcut>
              ) : null}
              {action.disabled && action.title ? (
                <span className="sr-only">{action.title}</span>
              ) : null}
            </ContextMenuItem>
          </Fragment>
        );
      })}
    </>
  );
};
