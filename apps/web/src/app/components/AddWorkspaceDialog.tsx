/**
 * VS Code "Add Folder to Workspace" quick-input.
 * Accepts a local absolute path, remote `cluster:/abs`, or `@registry-name`.
 */

import { type JSX, useCallback, useEffect, useState } from "react";
import { workspacesApi } from "@/api";
import { requestRemoteAuth } from "@/app/layout/remoteAuthPrompt";
import type { ServedWorkspaceSummary } from "@/app/types";
import { QuickInput } from "@/components/dialog/QuickInput";
export interface AddWorkspaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => void;
}

/** Heuristic: remote if cluster:/path, cluster:/path, or @registry-name. */
const detectKind = (raw: string): "local" | "remote" => {
  const s = raw.trim();
  if (s.startsWith("@")) return "remote";
  // SCP-style cluster:path (not Windows drive like C:\ or C:/ alone without host)
  if (/^[A-Za-z0-9._-]+@[^:]+:\//.test(s)) return "remote";
  if (/^[A-Za-z0-9._-]+:\//.test(s) && !/^[A-Za-z]:[/\\]/.test(s)) return "remote";
  return "local";
};

const shortFailure = (raw: string): string => {
  const t = raw.toLowerCase();
  if (t.includes("not found") || t.includes("404")) return "Path not found";
  if (t.includes("not a directory")) return "Not a directory";
  if (t.includes("already") || t.includes("exists")) return "Already in workspace";
  if (t.includes("target") && t.includes("not found")) return "Unknown remote target";
  return raw.length > 80 ? "Couldn't add folder" : raw || "Couldn't add folder";
};

export const AddWorkspaceDialog = ({
  open,
  onOpenChange,
  onAdded,
}: AddWorkspaceDialogProps): JSX.Element => {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setValue("");
      setHint(null);
      setBusy(false);
    }
  }, [open]);

  const submit = useCallback(async () => {
    const raw = value.trim();
    if (!raw || busy) return;
    setBusy(true);
    setHint(null);
    try {
      const kind = detectKind(raw);
      let added: ServedWorkspaceSummary;
      if (kind === "remote") {
        if (raw.startsWith("@")) {
          added = await workspacesApi.addWorkspace({
            kind: "remote",
            name: raw.slice(1),
            activate: true,
          });
        } else {
          added = await workspacesApi.addWorkspace({
            kind: "remote",
            path: raw,
            activate: true,
          });
        }
      } else {
        try {
          added = await workspacesApi.addWorkspace({
            kind: "local",
            path: raw,
            createIfMissing: false,
            activate: true,
          });
        } catch (first) {
          const msg = first instanceof Error ? first.message : String(first);
          if (msg.toLowerCase().includes("not found")) {
            // Offer create on second submit only when path missing — mirror Open Workspace.
            added = await workspacesApi.addWorkspace({
              kind: "local",
              path: raw,
              createIfMissing: true,
              activate: true,
            });
          } else {
            throw first;
          }
        }
      }
      onOpenChange(false);
      if (added.isRemote && (added.needsAuth || added.unreachable)) {
        requestRemoteAuth(added, "gesture");
      }
      onAdded();
    } catch (err) {
      setHint(shortFailure(err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  }, [value, busy, onOpenChange, onAdded]);

  return (
    <QuickInput
      open={open}
      onOpenChange={onOpenChange}
      title="Add folder to workspace"
      prompt="Add folder to workspace · a local path, cluster:/abs/path, or @name · ↵ to add, Esc to cancel"
      value={value}
      onValueChange={(next) => {
        setValue(next);
        if (hint) setHint(null);
      }}
      onSubmit={() => void submit()}
      placeholder="/path/to/workspace  or  cluster:/abs/path"
      error={hint}
      busy={busy}
      mono
    />
  );
};
