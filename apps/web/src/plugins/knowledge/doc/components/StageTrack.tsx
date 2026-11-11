/**
 * `<molab-stage-track>` (L10, Figma v2_02): a roadmap's stages left to right —
 * each a status glyph on a connector (the success colour after a finished
 * stage), its title, a muted line ("2 of 3 todos" / "blocked" / "not
 * started") and a small todo meter. A stage citing an experiment previews it
 * on click and opens it on double-click.
 */

import { Milestone as MilestoneIcon } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { StatusIcon } from "@/app/components/entity";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import { cn } from "@/lib/utils";
import type { StageProgress } from "../../campaignProgress";
import { usePlanCampaigns } from "../../PlanProgress";
import { type DocComponentProps, type DocComponentSpec, useDoc } from "../context";
import { ComponentFrame, ComponentLoading, ComponentNotice } from "../frame";
import { resolveDocRef } from "../RefChip";
import { hostOfDoc, pickCampaign, stageGlyph, stageLine, stageShare } from "./stageTrackModel";

const NAME = "molab-stage-track";

const Meter = ({ share }: { share: number }): JSX.Element => (
  <span aria-hidden className="mt-2 block h-1 w-4/5 overflow-hidden rounded-full bg-muted">
    <span
      className="block h-full rounded-full bg-status-completed"
      style={{ width: `${Math.round(share * 100)}%` }}
    />
  </span>
);

const StageBody = ({
  stage,
  target,
  children,
}: {
  stage: StageProgress;
  target: PreviewTarget | null;
  children: ReactNode;
}): JSX.Element => {
  const preview = usePreview();
  if (!target) return <div className="min-w-0">{children}</div>;
  return (
    <button
      type="button"
      title={stage.experiment}
      onClick={() => preview.preview(target)}
      onDoubleClick={() => preview.open(target)}
      className="block w-full min-w-0 rounded-control text-left outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
    >
      {children}
    </button>
  );
};

const Stage = ({
  stage,
  last,
  target,
}: {
  stage: StageProgress;
  last: boolean;
  target: PreviewTarget | null;
}): JSX.Element => {
  const glyph = stageGlyph(stage);
  return (
    <li className="min-w-0 flex-1">
      <div className="flex h-6 items-center gap-2">
        <StatusIcon status={glyph} className="size-icon" />
        {last ? null : (
          <span
            aria-hidden
            className={cn(
              "h-px flex-1",
              glyph === "succeeded" ? "bg-status-completed" : "bg-border",
            )}
          />
        )}
      </div>
      <StageBody stage={stage} target={target}>
        <span className="mt-2 block truncate text-body text-foreground">{stage.title}</span>
        <span className="mt-1 block truncate text-label text-muted-foreground">
          {stageLine(stage)}
        </span>
      </StageBody>
      <Meter share={stageShare(stage)} />
    </li>
  );
};

export const StageTrack = ({ attrs }: DocComponentProps): JSX.Element => {
  const doc = useDoc();
  const roadmap = attrs.roadmap?.trim() || undefined;
  const { campaigns, pending } = usePlanCampaigns(roadmap ? hostOfDoc(roadmap) : doc.hostPath);
  if (pending) return <ComponentLoading name={NAME} />;
  const campaign = pickCampaign(campaigns, { roadmap, relPath: doc.relPath, cls: doc.cls });
  if (!campaign) {
    return (
      <ComponentNotice name={NAME}>
        {roadmap ? `No roadmap at ${roadmap}.` : "No roadmap on this host. Set roadmap to one."}
      </ComponentNotice>
    );
  }
  const targetOf = (stage: StageProgress): PreviewTarget | null =>
    stage.experiment
      ? (resolveDocRef(stage.experiment, doc.refIndex, doc.snapshot)?.target ?? null)
      : null;
  const footer =
    campaign.roadmapPath === doc.relPath ? undefined : (
      <span className="truncate">{campaign.roadmapTitle}</span>
    );
  return (
    <ComponentFrame label={`Stages of ${campaign.roadmapTitle}`} footer={footer}>
      <ol className="flex gap-4 px-4 py-3">
        {campaign.stages.map((stage, index) => (
          <Stage
            key={stage.id}
            stage={stage}
            last={index === campaign.stages.length - 1}
            target={targetOf(stage)}
          />
        ))}
      </ol>
    </ComponentFrame>
  );
};

export const stageTrackSpec: DocComponentSpec = {
  name: NAME,
  label: "Stage track",
  description: "A roadmap's stages: glyph, todo meter; a stage opens its experiment.",
  keywords: ["roadmap", "stage", "progress", "plan"],
  icon: MilestoneIcon,
  template: {},
  Component: StageTrack,
};
