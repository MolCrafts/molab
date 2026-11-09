import { X } from "lucide-react";
import { type JSX, useEffect, useState } from "react";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import {
  getBottomPanelOpenRequest,
  listBottomPanels,
  subscribeBottomPanelHost,
  useWorkbenchGeneration,
} from "@/plugins/contributions/workbench";

/** Whether any plugin contributes a bottom panel — the toggle only shows then. */
export const useHasBottomPanels = (): boolean => {
  useWorkbenchGeneration();
  return listBottomPanels().length > 0;
};

/** A plugin's `openBottomPanel(id)` opens the region even while it is hidden. */
export const useBottomPanelOpenRequests = (onOpen: () => void): void => {
  useEffect(
    () =>
      subscribeBottomPanelHost(() => {
        if (getBottomPanelOpenRequest()) onOpen();
      }),
    [onOpen],
  );
};

interface PluginBottomPanelHostProps {
  /** The shell owns visibility (⌥J, the title-bar toggle). */
  onClose: () => void;
}

/**
 * VS Code panel (L00): caps panel tabs over the active contribution. Plugins
 * register via `api.panels.register({ position: "bottom", ... })`; the shell
 * places this region under the editor and sizes it.
 */
export const PluginBottomPanelHost = ({
  onClose,
}: PluginBottomPanelHostProps): JSX.Element | null => {
  useWorkbenchGeneration();
  const panels = listBottomPanels();
  const [selectedId, setSelectedId] = useState<string | null>(
    () => getBottomPanelOpenRequest()?.id ?? null,
  );

  useEffect(
    () =>
      subscribeBottomPanelHost(() => {
        const request = getBottomPanelOpenRequest();
        if (request) setSelectedId(request.id);
      }),
    [],
  );

  if (panels.length === 0) return null;

  const active = panels.find((panel) => panel.id === selectedId) ?? panels[0] ?? null;
  const PanelRender = active?.render;

  return (
    <section
      className="flex h-full min-h-0 flex-col border-t border-border bg-background"
      aria-label="Panel"
      data-shell-region="panel"
    >
      <div className="flex h-shell-tabs flex-none items-center gap-4 px-4">
        <div
          role="tablist"
          aria-label="Panels"
          className="flex h-full min-w-0 items-stretch gap-4 overflow-x-auto"
        >
          {panels.map((panel) => {
            const selected = panel.id === active?.id;
            return (
              <button
                key={panel.id}
                type="button"
                role="tab"
                aria-selected={selected}
                className={cn(
                  "relative flex-none text-micro font-medium uppercase tracking-wide outline-none",
                  "focus-visible:ring-1 focus-visible:ring-ring",
                  selected
                    ? "text-foreground after:absolute after:inset-x-0 after:bottom-1 after:h-px after:bg-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
                onClick={() => setSelectedId(panel.id)}
              >
                {panel.title}
              </button>
            );
          })}
        </div>
        <WorkbenchIconAction size="shell" label="Close Panel" className="ml-auto" onClick={onClose}>
          <X aria-hidden />
        </WorkbenchIconAction>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">{PanelRender ? <PanelRender /> : null}</div>
    </section>
  );
};
