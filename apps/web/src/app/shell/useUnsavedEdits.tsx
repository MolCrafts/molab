/**
 * One guard for an editor with unsaved edits (L06, L07): ⌘S saves, closing
 * the browser tab asks the browser, and leaving the editor in the app asks
 * through the L13 dialog. It also marks the editor tab ● (`dirtyEditors`).
 */

import { type JSX, useEffect } from "react";
import { type Location, useBlocker } from "react-router-dom";
import { AppDialog } from "@/components/dialog/AppDialog";
import { useMarkEditorDirty } from "./dirtyEditors";

export interface UnsavedEditsOptions {
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  /** What the dialog names: "the AlphaFold Baseline workflow", "README.md". */
  subject: string;
  /** The editor's page in the dirty-tab store (a base path, or a path with `?file=…`). */
  markPath: string | null;
  /**
   * Whether `next` is still this editor (no prompt). Default: same pathname —
   * the views of one page are one editor.
   */
  sameEditor?: (current: Location, next: Location) => boolean;
}

const samePathname = (current: Location, next: Location): boolean =>
  current.pathname === next.pathname;

export const useUnsavedEdits = ({
  dirty,
  saving,
  onSave,
  subject,
  markPath,
  sameEditor = samePathname,
}: UnsavedEditsOptions): JSX.Element => {
  useMarkEditorDirty(markPath, dirty);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        if (!dirty || saving) return;
        event.preventDefault();
        onSave();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dirty, saving, onSave]);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && !sameEditor(currentLocation, nextLocation),
  );
  useEffect(() => {
    if (blocker.state === "blocked" && !dirty) blocker.reset?.();
  }, [blocker, dirty]);

  return (
    <AppDialog
      open={blocker.state === "blocked"}
      onOpenChange={(open) => {
        if (!open) blocker.reset?.();
      }}
      size="confirm"
      danger
      title="Leave with unsaved changes?"
      message={`Your edits to ${subject} are not saved. Leaving discards them.`}
      primaryLabel="Leave"
      cancelLabel="Stay"
      onPrimary={() => blocker.proceed?.()}
    />
  );
};
