import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import {
  getBottomPanelOpenRequest,
  listBottomPanels,
  subscribeBottomPanelHost,
  useWorkbenchGeneration,
} from "@/plugins/contributions/workbench";

/**
 * VS Code–style bottom drawer. Default closed; plugins register via
 * `api.panels.register({ position: "bottom", ... })`. Status bar stays 28px
 * and non-expanding — this is a separate region above it.
 */
export const PluginBottomPanelHost = (): JSX.Element | null => {
  useWorkbenchGeneration();
  const panels = listBottomPanels();
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    return subscribeBottomPanelHost(() => {
      const request = getBottomPanelOpenRequest();
      if (request) setOpenId(request.id);
    });
  }, []);

  useEffect(() => {
    if (openId && !panels.some((panel) => panel.id === openId)) {
      setOpenId(null);
    }
  }, [openId, panels]);

  if (panels.length === 0) return null;

  const active = panels.find((panel) => panel.id === openId) ?? null;
  const open = active !== null;
  const heightRatio = active?.defaultSize ?? 0.28;
  const PanelRender = active?.render;

  return (
    <div className="flex shrink-0 flex-col border-t border-border bg-surface">
      <div className="flex h-[28px] items-center gap-1 overflow-x-auto px-1">
        {panels.map((panel) => {
          const selected = panel.id === openId;
          return (
            <button
              key={panel.id}
              type="button"
              className={cn(
                "h-[22px] shrink-0 rounded-control px-2 text-micro",
                selected
                  ? "bg-interactive text-interactive-foreground"
                  : "text-muted-foreground hover:bg-interactive/60 hover:text-foreground",
              )}
              onClick={() => setOpenId(selected ? null : panel.id)}
            >
              {panel.title}
            </button>
          );
        })}
      </div>
      {open && active && PanelRender ? (
        <div
          className="min-h-0 overflow-auto border-t border-border bg-canvas"
          style={{ height: `${Math.round(heightRatio * 100)}vh` }}
        >
          <PanelRender />
        </div>
      ) : null}
    </div>
  );
};
