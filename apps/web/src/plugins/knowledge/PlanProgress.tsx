import { useQueries } from "@tanstack/react-query";
import { type JSX, useMemo } from "react";
import { MixChart, StatusIcon } from "@/app/components/entity";
import { emptyCounts, type StatusKey } from "@/app/status/vocabulary";
import { buildCampaigns, type CampaignProgress } from "./campaignProgress";
import { knowledgeClassOf } from "./knowledgeClass";
import { knowledgeNoteQueryOptions, useKnowledgeListQuery } from "./queries";

const PLANNING = new Set(["Plan", "Roadmap", "Todo", "Milestone"]);

/**
 * Roadmaps with milestone and todo counts filled in. With `hostPath`, only the
 * planning documents hosted at or under that directory (a project and its
 * experiments) — so a project's Plan shows its own roadmap, not every one.
 */
export const usePlanCampaigns = (
  hostPath?: string,
): { campaigns: CampaignProgress[]; pending: boolean } => {
  const list = useKnowledgeListQuery();
  const heads = useMemo(
    () =>
      (list.data?.notes ?? []).filter(
        (note) =>
          PLANNING.has(knowledgeClassOf(note)) &&
          (hostPath === undefined || hostPath === "" || note.relPath.startsWith(`${hostPath}/`)),
      ),
    [list.data?.notes, hostPath],
  );
  const details = useQueries({
    queries: heads.map((note) => knowledgeNoteQueryOptions(note.relPath)),
  });
  const pending = list.isPending || details.some((query) => query.isPending);
  const campaigns = useMemo(() => {
    if (heads.length === 0 || pending) return [];
    return buildCampaigns(
      heads.map((note, index) => ({
        cls: knowledgeClassOf(note),
        name: note.name,
        relPath: note.relPath,
        record: details[index]?.data?.record,
      })),
    );
  }, [heads, details, pending]);
  return { campaigns, pending };
};

const STAGE_STATUS: Record<string, StatusKey> = {
  Met: "succeeded",
  Done: "succeeded",
  Missed: "failed",
  Blocked: "interrupted",
  Open: "pending",
};

const TODO_WORDING = {
  unit: ["todo", "todos"],
  words: { succeeded: "Done", queued: "Open", interrupted: "Blocked" },
} as const;

/** A stage's todos as the status mix the meter draws: done · open · blocked. */
const stageGroups = (campaign: CampaignProgress) =>
  campaign.stages.map((stage) => ({
    id: stage.id,
    label: stage.title,
    counts: {
      ...emptyCounts(),
      total: stage.todos.total,
      succeeded: stage.todos.done,
      queued: stage.todos.open,
      interrupted: stage.todos.blocked,
    },
  }));

/**
 * One roadmap per section (Figma L02-5): its stages as todo meters (done ·
 * open · blocked; a bar opens the stage's experiment), then one row per stage —
 * its word, its experiment, its milestone. Renders nothing without a roadmap.
 */
export const PlanProgress = ({
  campaigns,
  hostLabel,
  onOpenExperiment,
  onOpenDoc,
}: {
  campaigns: readonly CampaignProgress[];
  /** The roadmap's host (its project) when the page lists several hosts' roadmaps. */
  hostLabel?: (roadmapPath: string) => string | null;
  onOpenExperiment?: (name: string) => void;
  onOpenDoc?: (path: string) => void;
}): JSX.Element | null => {
  if (campaigns.length === 0) return null;

  return (
    <section aria-label="Plan progress" className="space-y-8">
      {campaigns.map((campaign) => (
        <div key={campaign.roadmapPath} className="space-y-4">
          <div className="flex items-baseline gap-2 text-body">
            <button
              type="button"
              className="font-medium text-foreground hover:underline"
              onClick={() => onOpenDoc?.(campaign.roadmapPath)}
            >
              {campaign.roadmapTitle}
            </button>
            {hostLabel?.(campaign.roadmapPath) ? (
              <span className="text-label text-muted-foreground">
                · {hostLabel(campaign.roadmapPath)}
              </span>
            ) : null}
            {campaign.planTitle ? (
              <button
                type="button"
                className="text-label text-muted-foreground hover:underline"
                onClick={() => campaign.planPath && onOpenDoc?.(campaign.planPath)}
              >
                {campaign.planTitle}
              </button>
            ) : null}
            <span className="ml-auto truncate font-mono text-label text-muted-foreground">
              {campaign.roadmapPath}
            </span>
          </div>
          {campaign.stages.some((stage) => stage.todos.total > 0) ? (
            <MixChart
              groups={stageGroups(campaign)}
              label={`Todos by stage of ${campaign.roadmapTitle}`}
              wording={TODO_WORDING}
              onPick={(id) => {
                const stage = campaign.stages.find((item) => item.id === id);
                if (stage?.experiment) onOpenExperiment?.(stage.experiment);
              }}
            />
          ) : null}
          <ol className="max-w-[48rem] divide-y divide-border border-y border-border">
            {campaign.stages.map((stage) => (
              <li key={stage.id} className="flex min-h-10 items-center gap-3 py-1">
                <StatusIcon
                  status={STAGE_STATUS[stage.word] ?? "pending"}
                  className="size-icon shrink-0"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-body text-foreground">{stage.title}</span>
                  <span className="block truncate text-label text-muted-foreground">
                    {stage.word}
                    {stage.todos.total > 0
                      ? ` · ${stage.todos.done} of ${stage.todos.total} todos${
                          stage.todos.blocked > 0 ? `, ${stage.todos.blocked} blocked` : ""
                        }`
                      : ""}
                    {stage.milestone ? ` · ${stage.milestone.criterion}` : ""}
                  </span>
                </span>
                {stage.experiment ? (
                  <button
                    type="button"
                    className="shrink-0 font-mono text-label text-muted-foreground hover:text-foreground hover:underline"
                    onClick={() => onOpenExperiment?.(stage.experiment ?? "")}
                  >
                    {stage.experiment}
                  </button>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
};
