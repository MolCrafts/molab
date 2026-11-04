import { useQueries } from "@tanstack/react-query";
import { type JSX, useMemo } from "react";
import { buildCampaigns } from "./campaignProgress";
import { knowledgeClassOf } from "./knowledgeClass";
import { knowledgeNoteQueryOptions, useKnowledgeListQuery } from "./queries";

const PLANNING = new Set(["Plan", "Roadmap", "Todo", "Milestone"]);

/**
 * Roadmap stages with the milestone and todo counts that say how far the
 * campaign has got. Renders nothing when this workspace has no roadmap.
 */
export const PlanProgress = ({
  onOpenExperiment,
  onOpenDoc,
}: {
  onOpenExperiment?: (name: string) => void;
  onOpenDoc?: (path: string) => void;
}): JSX.Element | null => {
  const list = useKnowledgeListQuery();
  const heads = useMemo(
    () => (list.data?.notes ?? []).filter((note) => PLANNING.has(knowledgeClassOf(note))),
    [list.data?.notes],
  );
  const details = useQueries({
    queries: heads.map((note) => knowledgeNoteQueryOptions(note.relPath)),
  });
  const campaigns = useMemo(() => {
    if (heads.length === 0 || details.some((query) => query.isPending)) return [];
    return buildCampaigns(
      heads.map((note, index) => ({
        cls: knowledgeClassOf(note),
        name: note.name,
        relPath: note.relPath,
        record: details[index]?.data?.record,
      })),
    );
  }, [heads, details]);

  if (campaigns.length === 0) return null;

  return (
    <section aria-label="Plan progress" className="mb-8 space-y-5">
      <h2 className="text-body font-medium text-foreground">Plan</h2>
      {campaigns.map((campaign) => (
        <div key={campaign.roadmapPath} className="space-y-2">
          <p className="text-label text-muted-foreground">
            {campaign.planTitle ? (
              <button
                type="button"
                className="text-foreground hover:underline"
                onClick={() => campaign.planPath && onOpenDoc?.(campaign.planPath)}
              >
                {campaign.planTitle}
              </button>
            ) : null}
            {campaign.planTitle ? " · " : null}
            <button
              type="button"
              className="hover:underline"
              onClick={() => onOpenDoc?.(campaign.roadmapPath)}
            >
              {campaign.roadmapTitle}
            </button>
          </p>
          <ol className="divide-y divide-border/60 border-y border-border/60">
            {campaign.stages.map((stage, index) => (
              <li
                key={stage.id}
                className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] gap-x-3 py-2"
              >
                <span className="font-mono text-micro text-muted-foreground">{index + 1}</span>
                <span className="min-w-0">
                  <span className="block text-body text-foreground">{stage.title}</span>
                  <span className="mt-0.5 block text-label text-muted-foreground">
                    {stage.experiment ? (
                      <button
                        type="button"
                        className="font-mono hover:underline"
                        onClick={() => onOpenExperiment?.(stage.experiment ?? "")}
                      >
                        {stage.experiment}
                      </button>
                    ) : (
                      <span className="font-mono">{stage.id}</span>
                    )}
                    {stage.todos.total > 0
                      ? ` · ${stage.todos.done}/${stage.todos.total} done${
                          stage.todos.blocked > 0 ? `, ${stage.todos.blocked} blocked` : ""
                        }`
                      : ""}
                    {stage.milestone ? ` · ${stage.milestone.criterion}` : ""}
                  </span>
                </span>
                <span className="text-micro text-muted-foreground">{stage.word}</span>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
};
