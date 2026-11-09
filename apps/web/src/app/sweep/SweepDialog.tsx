/**
 * Seed one pending run per cell of a parameter grid.
 *
 * The editor is {@link SweepAxesEditor}. This dialog compiles the draft and
 * calls the seed endpoint, which skips cells that already exist.
 */

import { type JSX, useEffect, useRef, useState } from "react";
import { apiErrorMessage } from "@/api/errors";
import { sweepApi } from "@/api/sweep";
import { missingCellCount } from "@/app/renderers/experiment/experimentStory";
import { AppDialog } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";
import { type AxisDraft, compileSweep, draftsFromParameterSpace } from "./grid";
import { SweepAxesEditor } from "./SweepAxesEditor";

export interface SweepDialogProps {
  projectId: string;
  experimentId: string;
  parameterSpace?: Record<string, unknown>;
  /** Runs the experiment already has: their combinations are not created again. */
  runs?: readonly { parameters?: Record<string, unknown> }[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (created: number) => void;
}

export const SweepDialog = ({
  projectId,
  experimentId,
  parameterSpace,
  runs = [],
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
        created === 0
          ? `All ${seeded.cells} combinations already exist`
          : `${created} runs created`,
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
  // The server keeps existing cells; say how many are new before anything is sent.
  const fresh = "grid" in compiled ? missingCellCount(compiled.grid.axes, runs) : null;

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Sweep"
      // Axes are typed value by value: ↵ must not seed a grid half-written.
      submitOnEnter={false}
      message={
        cells === null || fresh === null
          ? "One run per combination of the values below."
          : `${cells} ${cells === 1 ? "combination" : "combinations"} · ${cells - fresh} already run · ${fresh} new`
      }
      size="wide"
      primaryLabel={
        fresh === null ? "Create runs" : `Create ${fresh} ${fresh === 1 ? "run" : "runs"}`
      }
      busyLabel="Creating…"
      busy={busy}
      primaryDisabled={cells === null || fresh === 0}
      onPrimary={submit}
      error={error}
    >
      <SweepAxesEditor drafts={drafts} disabled={busy} onChange={setDrafts} />
    </AppDialog>
  );
};
