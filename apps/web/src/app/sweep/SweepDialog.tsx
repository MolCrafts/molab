/**
 * Seed one pending run per cell of a parameter grid.
 *
 * The editor is {@link SweepAxesEditor}. This dialog compiles the draft and
 * calls the seed endpoint, which skips cells that already exist.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@molcrafts/ui";
import { Check } from "lucide-react";
import { type JSX, useEffect, useRef, useState } from "react";
import { apiErrorMessage } from "@/api/errors";
import { sweepApi } from "@/api/sweep";
import { toast } from "@/components/ui/toast";
import { WorkbenchAction } from "@/components/workbench";
import { type AxisDraft, compileSweep, draftsFromParameterSpace } from "./grid";
import { SweepAxesEditor } from "./SweepAxesEditor";

export interface SweepDialogProps {
  projectId: string;
  experimentId: string;
  parameterSpace?: Record<string, unknown>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (created: number) => void;
}

export const SweepDialog = ({
  projectId,
  experimentId,
  parameterSpace,
  open,
  onOpenChange,
  onCreated,
}: SweepDialogProps): JSX.Element => {
  const [drafts, setDrafts] = useState<AxisDraft[]>(() => draftsFromParameterSpace(parameterSpace));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wasOpen = useRef(false);
  const compiled = compileSweep(drafts);

  useEffect(() => {
    if (open && !wasOpen.current) {
      setDrafts(draftsFromParameterSpace(parameterSpace));
      setError(null);
    }
    wasOpen.current = open;
  }, [open, parameterSpace]);

  const submit = async (): Promise<void> => {
    if ("error" in compiled) {
      setError(compiled.error);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const seeded = await sweepApi.seed(projectId, experimentId, compiled.grid.axes);
      const created = seeded.created.length;
      toast.success(
        created === 0 ? `${seeded.cells} cells already exist` : `${created} runs seeded`,
      );
      onOpenChange(false);
      onCreated(created);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not seed the sweep."));
    } finally {
      setBusy(false);
    }
  };

  const cells = "grid" in compiled ? compiled.grid.cells : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Sweep</DialogTitle>
          <DialogDescription>
            {cells === null
              ? "One run per combination. Existing cells are kept."
              : `${cells} run${cells === 1 ? "" : "s"}. Existing cells are kept.`}
          </DialogDescription>
        </DialogHeader>
        <SweepAxesEditor drafts={drafts} disabled={busy} onChange={setDrafts} />
        {error ? <p className="text-body text-destructive">{error}</p> : null}
        <DialogFooter>
          <WorkbenchAction
            icon={<Check aria-hidden />}
            kind="primary"
            size="default"
            disabled={busy || cells === null}
            onClick={() => void submit()}
          >
            {busy ? "Seeding…" : "Seed runs"}
          </WorkbenchAction>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
