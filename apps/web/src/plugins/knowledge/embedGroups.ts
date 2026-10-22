import type { EmbedTargetKind } from "@/api";

/** One slash-menu row. `target` is what embed sends; a run's target is its ref. */
export interface EmbedGroupItem {
  id: string;
  label: string;
  target: string;
}

export interface EmbedGroup {
  kind: EmbedTargetKind;
  label: string;
  items: EmbedGroupItem[];
}

interface NamedEntity {
  id: string;
  name: string;
}

interface RunEntity extends NamedEntity {
  ref?: string;
}

/**
 * Slash-menu embed groups. A run is offered only when the server sent `ref`,
 * and that string is the embed target. Experiments and assets embed by id.
 * Empty groups are dropped.
 */
export const buildEmbedGroups = (snapshot: {
  experiments: NamedEntity[];
  runs: RunEntity[];
  assets: NamedEntity[];
}): EmbedGroup[] =>
  [
    {
      kind: "experiment" as const,
      label: "Experiments",
      items: snapshot.experiments.map((entity) => ({
        id: entity.id,
        label: entity.name,
        target: entity.id,
      })),
    },
    {
      kind: "run" as const,
      label: "Runs",
      items: snapshot.runs.flatMap((run) =>
        run.ref ? [{ id: run.id, label: run.name || run.id, target: run.ref }] : [],
      ),
    },
    {
      kind: "asset" as const,
      label: "Assets",
      items: snapshot.assets.map((entity) => ({
        id: entity.id,
        label: entity.name,
        target: entity.id,
      })),
    },
  ].filter((group) => group.items.length > 0);
