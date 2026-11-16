/**
 * Editor tab row (L00): 35px; tabs scroll horizontally, ⌄ lists every open
 * tab, and the right end holds the editor actions a page hands over. A tab is
 * icon (or the run's status glyph) + label + ✕; middle-click closes.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { ChevronDown, X } from "lucide-react";
import { type JSX, type Ref, useEffect, useRef } from "react";
import { StatusIcon } from "@/app/components/entity/StatusIcon";
import { isEditorDirty, useDirtyEditors } from "@/app/shell/dirtyEditors";
import type { WorkspaceSnapshot } from "@/app/types";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import { describeEditorTab, type EditorTabPresentation } from "./describeEditorTab";
import type { EditorTab, EditorTabsState } from "./editorTabs";
import { SHORTCUTS } from "./keys";
import { useTabSnapshot } from "./useTabSnapshot";

interface EditorTabStripProps {
  state: EditorTabsState;
  snapshot: WorkspaceSnapshot;
  onActivate: (key: string) => void;
  onClose: (key: string) => void;
  /** Double-click pins an italic preview tab. */
  onPin: (key: string) => void;
  /** Receives the editor-actions slot element. */
  actionsRef: Ref<HTMLDivElement>;
}

const TabGlyph = ({ presentation }: { presentation: EditorTabPresentation }): JSX.Element => {
  if (presentation.status) {
    return <StatusIcon status={presentation.status} className="size-icon" />;
  }
  const Icon = presentation.icon;
  return <Icon className="size-icon flex-none text-muted-foreground" aria-hidden />;
};

const tabTitle = (presentation: EditorTabPresentation): string =>
  presentation.context ? `${presentation.label} — ${presentation.context}` : presentation.label;

export const EditorTabStrip = ({
  state,
  snapshot,
  onActivate,
  onClose,
  onPin,
  actionsRef,
}: EditorTabStripProps): JSX.Element => {
  const strip = useRef<HTMLDivElement>(null);
  // The row scrolls; keep the active tab in view.
  useEffect(() => {
    if (!state.activeKey) return;
    strip.current
      ?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')
      ?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [state.activeKey]);

  const dirtyEditors = useDirtyEditors();
  const tabSnapshot = useTabSnapshot(snapshot);
  const described = state.tabs.map((tab): [EditorTab, EditorTabPresentation] => [
    tab,
    describeEditorTab(tab, tabSnapshot),
  ]);

  return (
    <div className="flex h-shell-tabs flex-none items-stretch border-b border-border bg-surface-subtle">
      <div
        ref={strip}
        role="tablist"
        aria-label="Open editors"
        className="flex min-w-0 flex-1 items-stretch overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {described.map(([tab, presentation]) => {
          const active = tab.key === state.activeKey;
          const dirty = isEditorDirty(dirtyEditors, tab.path);
          return (
            <div
              key={tab.key}
              className={cn(
                "group relative flex max-w-shell-tab-max flex-none items-center border-r border-border",
                active ? "bg-background" : "hover:bg-interactive",
                // VS Code: the active tab's top edge carries the accent.
                active && "after:absolute after:inset-x-0 after:top-0 after:h-px after:bg-accent",
              )}
              onAuxClick={(event) => {
                if (event.button === 1) {
                  event.preventDefault();
                  onClose(tab.key);
                }
              }}
            >
              <button
                type="button"
                role="tab"
                aria-selected={active}
                title={tab.preview ? `${tabTitle(presentation)} (preview)` : tabTitle(presentation)}
                className={cn(
                  "flex h-full min-w-0 items-center gap-2 pr-1 pl-3 text-body outline-none",
                  "focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
                  active ? "text-foreground" : "text-muted-foreground",
                )}
                onClick={() => onActivate(tab.key)}
                onDoubleClick={() => onPin(tab.key)}
              >
                <TabGlyph presentation={presentation} />
                <span
                  className={cn(
                    "truncate",
                    tab.preview && "italic",
                    tab.kind === "run" && "font-mono text-label",
                  )}
                >
                  {presentation.label}
                </span>
              </button>
              <WorkbenchIconAction
                size="shell"
                label={
                  dirty ? `Close ${presentation.label} (unsaved)` : `Close ${presentation.label}`
                }
                shortcut={active ? SHORTCUTS.closeEditor() : undefined}
                className={cn(
                  "mr-1 text-foreground",
                  !active && !dirty && "invisible group-focus-within:visible group-hover:visible",
                )}
                onClick={() => onClose(tab.key)}
              >
                {/* VS Code: unsaved edits show ● where ✕ is, until the tab is hovered. */}
                {dirty ? (
                  <>
                    <span
                      aria-hidden
                      className="size-2 rounded-full bg-foreground group-focus-within:hidden group-hover:hidden"
                    />
                    <X aria-hidden className="hidden group-focus-within:block group-hover:block" />
                  </>
                ) : (
                  <X aria-hidden />
                )}
              </WorkbenchIconAction>
            </div>
          );
        })}
      </div>
      {state.tabs.length > 1 ? (
        <div className="flex flex-none items-center px-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <WorkbenchIconAction size="shell" label="Open editors">
                <ChevronDown aria-hidden />
              </WorkbenchIconAction>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="max-w-sm">
              {described.map(([tab, presentation]) => (
                <DropdownMenuItem
                  key={tab.key}
                  className={cn(tab.key === state.activeKey && "bg-accent-muted")}
                  onSelect={() => onActivate(tab.key)}
                >
                  <TabGlyph presentation={presentation} />
                  <span className={cn("truncate", tab.preview && "italic")}>
                    {presentation.label}
                  </span>
                  {presentation.context ? (
                    <span className="ml-auto truncate pl-3 text-micro text-muted-foreground">
                      {presentation.context}
                    </span>
                  ) : null}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ) : null}
      <div
        ref={actionsRef}
        className="flex flex-none items-center gap-1 px-2 empty:hidden"
        data-slot="editor-actions"
      />
    </div>
  );
};
