/**
 * VS Code quick-input style: top-centered, one line of chrome, enter to submit.
 */

import { type JSX, useCallback, useEffect, useState } from "react";
import { workspacesApi } from "@/api";
import type { ServedWorkspaceSummary } from "@/app/types";
import { QuickInput } from "@/components/dialog/QuickInput";
import { parseHostQualifiedLabel } from "@/lib/workspace-path";
export interface RemoteConnectDialogProps {
  workspace: ServedWorkspaceSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** User pressed Esc. Distinct from the dialog closing after a successful login. */
  onDismiss?: () => void;
  onConnected: () => void;
}

const shortFailure = (raw: string): string => {
  const t = raw.toLowerCase();
  if (t === "auth") return "Authentication rejected";
  if (t === "timeout") return "Timed out";
  if (t === "unreachable") return "Host unavailable";
  if (t.includes("empty")) return "Enter a code";
  return raw || "Couldn't connect";
};

export const RemoteConnectDialog = ({
  workspace,
  open,
  onOpenChange,
  onDismiss,
  onConnected,
}: RemoteConnectDialogProps): JSX.Element => {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setCode("");
      setHint(null);
      setBusy(false);
    }
    // Clear the OTP field when the target workspace changes.
    void workspace?.key;
  }, [open, workspace?.key]);

  const submit = useCallback(async () => {
    if (!workspace || !code.trim() || busy) return;
    setBusy(true);
    setHint(null);
    try {
      await workspacesApi.connectWorkspace(workspace.key, code.trim());
      onOpenChange(false);
      onConnected();
    } catch (err) {
      setHint(shortFailure(err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  }, [workspace, code, busy, onOpenChange, onConnected]);

  const host = workspace ? (parseHostQualifiedLabel(workspace.label)?.host ?? "remote") : "remote";

  // L13: a quick input that must be answered — no outside click; Esc dismisses.
  return (
    <QuickInput
      open={open}
      onOpenChange={onOpenChange}
      title={`Connect to ${host}`}
      prompt={`Connect to ${host} · verification code · ↵ to connect, Esc to dismiss`}
      value={code}
      onValueChange={(next) => {
        setCode(next);
        if (hint) setHint(null);
      }}
      onSubmit={() => void submit()}
      placeholder="Verification code"
      error={hint}
      busy={busy}
      mono
      blocking
      onEscape={() => {
        onDismiss?.();
        onOpenChange(false);
      }}
      inputProps={{ autoComplete: "one-time-code", inputMode: "numeric" }}
    />
  );
};
