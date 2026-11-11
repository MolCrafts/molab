/**
 * Harvest a terminal run into Knowledge — Dialog form (replaces window.prompt).
 */

import {
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "@molcrafts/ui";
import { BookMarked } from "lucide-react";
import { type JSX, useState } from "react";
import { AppDialog } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";

const KINDS = ["Finding", "Observation", "Report"] as const;

interface HarvestDialogProps {
  projectId: string;
  experimentId: string;
  runId: string;
  onHarvested: (path: string) => void;
  /** Omit with `open` given: the caller opens it (a menu item). */
  trigger?: JSX.Element | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function HarvestDialog({
  projectId,
  experimentId,
  runId,
  onHarvested,
  trigger,
  open: controlledOpen,
  onOpenChange,
}: HarvestDialogProps): JSX.Element {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = (next: boolean): void => {
    setLocalOpen(next);
    onOpenChange?.(next);
  };
  const [kind, setKind] = useState<string>("Finding");
  const [narrative, setNarrative] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [narrativeError, setNarrativeError] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    const text = narrative.trim();
    if (!text) {
      setNarrativeError("Narrative required.");
      return;
    }
    setNarrativeError(null);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(experimentId)}/runs/${encodeURIComponent(runId)}/harvest`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            cls: kind,
            narrative: text,
            created_by: "ui",
          }),
        },
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || res.statusText);
      }
      const body = (await res.json()) as { name?: string; path?: string };
      const path = body.path?.trim() || "";
      setOpen(false);
      setNarrative("");
      toast.success("Harvested");
      onHarvested(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setError(null);
          setNarrativeError(null);
        }
      }}
      title="Harvest"
      size="form"
      primaryLabel="Save"
      busyLabel="Saving…"
      busy={busy}
      primaryDisabled={!narrative.trim()}
      onPrimary={submit}
      error={error}
      trigger={
        trigger === null
          ? undefined
          : (trigger ?? (
              <WorkbenchIconAction label="Harvest to knowledge">
                <BookMarked className="size-3.5" />
              </WorkbenchIconAction>
            ))
      }
    >
      <div className="grid gap-2">
        <Label htmlFor="harvest-kind">Kind</Label>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger id="harvest-kind">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {KINDS.map((k) => (
              <SelectItem key={k} value={k}>
                {k}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="harvest-narrative">Narrative</Label>
        <Textarea
          id="harvest-narrative"
          value={narrative}
          onChange={(e) => setNarrative(e.target.value)}
          rows={4}
          placeholder="What does this run mean?"
          disabled={busy}
          aria-invalid={narrativeError ? true : undefined}
        />
        {narrativeError ? (
          <p
            className="flex items-center gap-1 text-label text-status-failed-foreground"
            role="alert"
          >
            {narrativeError}
          </p>
        ) : null}
      </div>
    </AppDialog>
  );
}
