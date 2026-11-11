/**
 * `<molab-milestone>` (L10, Figma v2_02): a Milestone record — its status
 * glyph, the criterion, the evidence cited so far (`evidence` = space-separated
 * `molab:` refs, drawn as chips), and "Mark met" while it is open.
 */

import { Flag } from "lucide-react";
import type { JSX } from "react";
import { StatusIcon } from "@/app/components/entity";
import { DialogButton } from "@/components/dialog/AppDialog";
import { planningView } from "../../planningModel";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentFrame, ComponentLoading, ComponentNotice } from "../frame";
import { RefChip } from "../RefChip";
import { useRecordSource } from "./useRecordSource";

const NAME = "molab-milestone";

const GLYPH: Record<string, string> = { met: "succeeded", missed: "failed", open: "pending" };

const evidenceRefs = (text: string | undefined): string[] =>
  (text ?? "").split(/\s+/).filter((part) => part.startsWith("molab:"));

export const Milestone = ({ attrs }: DocComponentProps): JSX.Element => {
  const source = useRecordSource(attrs.src);
  if (source.state === "loading") return <ComponentLoading name={NAME} />;
  if (source.state === "missing")
    return <ComponentNotice name={NAME}>{source.message}</ComponentNotice>;
  if (!attrs.src && source.cls !== "Milestone") {
    return (
      <ComponentNotice name={NAME}>Set src to the path of a Milestone document.</ComponentNotice>
    );
  }
  const view = planningView("Milestone", source.record);
  if (view?.kind !== "milestone") {
    return <ComponentNotice name={NAME}>The record has no stage and criterion.</ComponentNotice>;
  }
  const evidence = evidenceRefs(attrs.evidence);
  const markMet = (): void => source.commit({ ...source.record, status: "met" });
  return (
    <ComponentFrame label="Milestone">
      <div className="flex items-start gap-3 px-3 py-3">
        <StatusIcon status={GLYPH[view.status] ?? "pending"} className="mt-1 size-icon" />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-body text-foreground">{view.criterion}</p>
          {evidence.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {evidence.map((ref) => (
                <RefChip key={ref} refText={ref} />
              ))}
            </div>
          ) : null}
          {source.error ? (
            <p role="alert" className="text-label text-status-failed-foreground">
              {source.error}
            </p>
          ) : null}
        </div>
        {view.status === "open" && source.writable ? (
          <DialogButton kind="secondary" size="chrome" type="button" onClick={markMet}>
            Mark met
          </DialogButton>
        ) : null}
      </div>
    </ComponentFrame>
  );
};

export const milestoneSpec: DocComponentSpec = {
  name: NAME,
  label: "Milestone",
  description: "A milestone's criterion, its evidence, and Mark met.",
  keywords: ["milestone", "criterion", "checkpoint", "met"],
  icon: Flag,
  template: {},
  Component: Milestone,
};
