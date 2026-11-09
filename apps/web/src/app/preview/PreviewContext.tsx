/**
 * The one Preview (L12): which target is shown, and the verbs every list,
 * chart and tree uses — `preview` on a single click, `open` on double-click /
 * ↵ / ↗. Outside the shell (tests, a page rendered alone) the context has no
 * provider; `preview` then opens, so a click is never lost.
 */

import { createContext, type JSX, type ReactNode, useCallback, useContext, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { workspaceApi } from "@/api";
import type { ServedWorkspaceSummary } from "@/app/types";
import { reportStatus } from "@/lib/status-report";
import { type PreviewTarget, previewKey, previewPath } from "./target";

export interface PreviewControls {
  target: PreviewTarget | null;
  preview: (target: PreviewTarget) => void;
  close: () => void;
  /**
   * Open the target's page in the active editor tab (`path` for a specific
   * view, e.g. the run's Logs); `background` keeps the current tab.
   */
  open: (target: PreviewTarget, options?: { background?: boolean; path?: string }) => void;
  isPreviewed: (target: PreviewTarget) => boolean;
}

const PreviewContext = createContext<PreviewControls | null>(null);

/** Activate the served workspace a run lives in before routing to it. */
const useOpenTarget = (
  workspaces: readonly ServedWorkspaceSummary[],
): ((target: PreviewTarget, path?: string) => void) => {
  const navigate = useNavigate();
  return useCallback(
    (target: PreviewTarget, path?: string) => {
      const key = "workspaceKey" in target ? target.workspaceKey : undefined;
      const workspace = key ? workspaces.find((item) => item.key === key) : undefined;
      const go = async (): Promise<void> => {
        if (workspace && !workspace.active) await workspaceApi.activate(workspace);
        navigate(path ?? previewPath(target));
      };
      void go().catch((error) =>
        reportStatus(error instanceof Error ? error.message : "Could not open workspace", "error"),
      );
    },
    [navigate, workspaces],
  );
};

interface PreviewProviderProps {
  target: PreviewTarget | null;
  onTargetChange: (target: PreviewTarget | null) => void;
  workspaces: readonly ServedWorkspaceSummary[];
  /** Background open: the shell adds a tab without leaving the current one. */
  onOpenInBackground?: (path: string, label: string) => void;
  children: ReactNode;
}

export const PreviewProvider = ({
  target,
  onTargetChange,
  workspaces,
  onOpenInBackground,
  children,
}: PreviewProviderProps): JSX.Element => {
  const openTarget = useOpenTarget(workspaces);
  const value = useMemo<PreviewControls>(
    () => ({
      target,
      preview: (next) => onTargetChange(next),
      close: () => onTargetChange(null),
      open: (next, options) => {
        const key = "workspaceKey" in next ? next.workspaceKey : undefined;
        const foreign = Boolean(key && workspaces.some((item) => item.key === key && !item.active));
        // A tab belongs to the active workspace's set: another workspace opens in front.
        if (options?.background && onOpenInBackground && !foreign) {
          onOpenInBackground(options.path ?? previewPath(next), previewKey(next));
          return;
        }
        onTargetChange(null);
        openTarget(next, options?.path);
      },
      isPreviewed: (candidate) => target !== null && previewKey(target) === previewKey(candidate),
    }),
    [target, onTargetChange, onOpenInBackground, openTarget, workspaces],
  );
  return <PreviewContext.Provider value={value}>{children}</PreviewContext.Provider>;
};

/** Outside the shell nothing is previewed; a preview request opens the page. */
const DETACHED: PreviewControls = {
  target: null,
  preview: (target) => window.location.assign(previewPath(target)),
  close: () => {},
  open: (target, options) => window.location.assign(options?.path ?? previewPath(target)),
  isPreviewed: () => false,
};

export const usePreview = (): PreviewControls => useContext(PreviewContext) ?? DETACHED;
