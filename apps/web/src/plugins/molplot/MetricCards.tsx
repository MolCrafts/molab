/**
 * Cards for the record types that are not scalars: histograms, text, JSON and
 * images — one card per key, grouped by `buildMetricCards`. Scalars keep their
 * series tiles in `RunMetricsView`.
 */

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Slider,
} from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import { ImageOff } from "lucide-react";
import { type JSX, type ReactNode, useMemo, useState } from "react";
import { runFileBlobQueryOptions } from "@/app/state/entityQueries";
import { WorkbenchAction, WorkbenchTag } from "@/components/workbench";
import { useObjectUrl } from "@/lib/use-object-url";
import { cn } from "@/lib/utils";
import { MolplotBarChart } from "./MolplotBarChart";
import {
  buildHistogramBarConfig,
  type CardEntry,
  type Histogram,
  type ImageRef,
  isAttemptRelative,
  type MetricCard,
} from "./metric-cards";

/** Where an attempt lives, as the file routes address it. */
export interface AttemptCoords {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
}

const stepLabel = (step: number | null): string => (step === null ? "no step" : `step ${step}`);

/** "replayed from e01": these records came from the node cache, not this attempt. */
export const ReplayMarker = ({ sources }: { sources: readonly string[] }): JSX.Element | null =>
  sources.length === 0 ? null : (
    <WorkbenchTag
      mono
      data-replayed-from={sources.join(",")}
      title={`Written by ${sources.join(", ")}; this attempt replayed them from the node cache.`}
    >
      replayed from {sources.join(", ")}
    </WorkbenchTag>
  );

/** Chips that narrow every card to the records one task wrote. */
export const TaskFilter = ({
  tasks,
  value,
  onChange,
}: {
  tasks: readonly string[];
  value: string | null;
  onChange: (task: string | null) => void;
}): JSX.Element => (
  <fieldset aria-label="Filter by task" className="flex flex-wrap items-center gap-1">
    <span className="mr-1 text-micro text-muted-foreground">Task</span>
    {[null, ...tasks].map((task) => (
      <WorkbenchAction
        key={task ?? "_all"}
        kind={value === task ? "primary" : "ghost"}
        size="compact"
        aria-pressed={value === task}
        onClick={() => onChange(task)}
        className={cn(task !== null && "font-mono")}
      >
        {task ?? "all"}
      </WorkbenchAction>
    ))}
  </fieldset>
);

const CardFrame = ({
  kind,
  title,
  meta,
  replayedFrom,
  children,
}: {
  kind: string;
  title: string;
  meta?: ReactNode;
  replayedFrom: readonly string[];
  children: ReactNode;
}): JSX.Element => (
  <article data-card={kind} data-key={title} className="min-w-0 p-3">
    <header className="flex items-baseline justify-between gap-3">
      <h4 className="min-w-0 flex-1 truncate text-body-lg font-medium text-foreground">{title}</h4>
      <div className="flex shrink-0 items-center gap-2">
        <ReplayMarker sources={replayedFrom} />
        {meta ? <span className="font-mono text-label text-muted-foreground">{meta}</span> : null}
      </div>
    </header>
    <div className="mt-1 min-w-0">{children}</div>
  </article>
);

/** A step picker over a card's entries: a slider, labelled with the step it lands on. */
const StepSlider = ({
  entries,
  index,
  onChange,
  label,
}: {
  entries: readonly CardEntry<unknown>[];
  index: number;
  onChange: (index: number) => void;
  label: string;
}): JSX.Element | null =>
  entries.length < 2 ? null : (
    <div className="mt-2 flex items-center gap-2">
      <Slider
        min={0}
        max={entries.length - 1}
        step={1}
        value={[index]}
        onValueChange={([next]) => onChange(next)}
        className="flex-1"
        aria-label={label}
      />
      <span className="w-24 shrink-0 text-right font-mono text-micro tabular-nums text-muted-foreground">
        {stepLabel(entries[index]?.step ?? null)}
      </span>
    </div>
  );

/** The selected entry: what the user picked, else the latest — which follows a live run. */
const usePickedEntry = <V,>(card: MetricCard<V>) => {
  const [picked, setPicked] = useState<number | null>(null);
  const last = card.entries.length - 1;
  const index = picked === null ? last : Math.min(picked, last);
  return {
    index,
    entry: card.entries[index],
    pick: (next: number) => setPicked(next >= last ? null : next),
  };
};

export const HistogramCard = ({
  card,
  color,
}: {
  card: MetricCard<Histogram>;
  color: string;
}): JSX.Element => {
  const { index, entry, pick } = usePickedEntry(card);
  const config = useMemo(
    () => buildHistogramBarConfig(card.key, entry.value, color),
    [card.key, entry.value, color],
  );
  return (
    <CardFrame
      kind="histogram"
      title={card.key}
      meta={stepLabel(entry.step)}
      replayedFrom={card.replayedFrom}
    >
      <MolplotBarChart config={config} style={{ width: "100%", height: "220px" }} />
      <StepSlider
        entries={card.entries}
        index={index}
        onChange={pick}
        label={`${card.key} histogram step`}
      />
    </CardFrame>
  );
};

/** How many text entries a card lists before it says how many it left out. */
const TEXT_ENTRY_LIMIT = 50;

export const TextCard = ({ card }: { card: MetricCard<string> }): JSX.Element => {
  const newestFirst = [...card.entries].reverse();
  const shown = newestFirst.slice(0, TEXT_ENTRY_LIMIT);
  return (
    <CardFrame
      kind="text"
      title={card.key}
      meta={`${card.entries.length} ${card.entries.length === 1 ? "entry" : "entries"}`}
      replayedFrom={card.replayedFrom}
    >
      <div className="divide-y divide-border border-y border-border">
        {shown.map((entry, position) => (
          <details key={entry.order} open={position === 0} className="group py-row-pad">
            <summary className="cursor-pointer select-none font-mono text-micro text-muted-foreground hover:text-foreground">
              {stepLabel(entry.step)}
              {entry.task ? ` · ${entry.task}` : ""}
            </summary>
            <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-label text-foreground">
              {entry.value}
            </pre>
          </details>
        ))}
      </div>
      {newestFirst.length > shown.length ? (
        <p className="mt-1 text-micro text-muted-foreground">
          {newestFirst.length - shown.length} older entries not shown.
        </p>
      ) : null}
    </CardFrame>
  );
};

const JsonLeaf = ({ value }: { value: unknown }): JSX.Element => (
  <span
    className={cn(
      typeof value === "string" ? "text-foreground" : "text-accent",
      value === null && "text-muted-foreground",
    )}
  >
    {typeof value === "string" ? JSON.stringify(value) : String(value)}
  </span>
);

/** A JSON value as a tree: objects and arrays fold, the first two levels start open. */
export const JsonTree = ({
  value,
  label,
  depth = 0,
}: {
  value: unknown;
  label?: string;
  depth?: number;
}): JSX.Element => {
  const name =
    label !== undefined ? <span className="text-muted-foreground">{label}: </span> : null;
  if (value === null || typeof value !== "object") {
    return (
      <div className="font-mono text-label">
        {name}
        <JsonLeaf value={value} />
      </div>
    );
  }
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.map((item, index) => [String(index), item])
    : Object.entries(value as Record<string, unknown>);
  const brackets = Array.isArray(value) ? ["[", "]"] : ["{", "}"];
  return (
    <details open={depth < 2} className="font-mono text-label">
      <summary className="cursor-pointer select-none">
        {name}
        <span className="text-muted-foreground">
          {brackets[0]}
          {entries.length}
          {brackets[1]}
        </span>
      </summary>
      <div className="ml-3 border-l border-border pl-2">
        {entries.map(([key, item]) => (
          <JsonTree key={key} label={key} value={item} depth={depth + 1} />
        ))}
      </div>
    </details>
  );
};

export const JsonCard = ({ card }: { card: MetricCard<unknown> }): JSX.Element => {
  const { index, entry, pick } = usePickedEntry(card);
  return (
    <CardFrame
      kind="json"
      title={card.key}
      meta={card.entries.length < 2 ? stepLabel(entry.step) : undefined}
      replayedFrom={card.replayedFrom}
    >
      {card.entries.length > 1 ? (
        <Select value={String(index)} onValueChange={(next) => pick(Number(next))}>
          <SelectTrigger className="mb-2 w-44" aria-label={`${card.key} step`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {card.entries
              .map((item, position) => (
                <SelectItem key={item.order} value={String(position)}>
                  {stepLabel(item.step)}
                  {position === card.entries.length - 1 ? " (latest)" : ""}
                </SelectItem>
              ))
              .reverse()}
          </SelectContent>
        </Select>
      ) : null}
      <div className="max-h-80 overflow-auto">
        <JsonTree value={entry.value} />
      </div>
    </CardFrame>
  );
};

/** The bytes of one image the attempt holds, through its own file route. */
export const imageBlobQueryOptions = (coords: AttemptCoords, path: string) =>
  runFileBlobQueryOptions(
    coords.projectId,
    coords.experimentId,
    coords.runId,
    coords.executionId,
    path,
  );

const ImageThumb = ({
  coords,
  entry,
  onOpen,
}: {
  coords: AttemptCoords;
  entry: CardEntry<ImageRef>;
  onOpen?: (path: string) => void;
}): JSX.Element => {
  const { path, caption } = entry.value;
  const inAttempt = isAttemptRelative(path);
  const blob = useQuery({ ...imageBlobQueryOptions(coords, path), enabled: inAttempt });
  const url = useObjectUrl(blob.data);
  const picture = url ? (
    <img src={url} alt={caption ?? path} className="h-full w-full object-contain" />
  ) : (
    <span className="flex h-full w-full flex-col items-center justify-center gap-1 p-2 text-center text-micro text-muted-foreground">
      {!inAttempt || blob.error ? <ImageOff className="size-icon-sm" aria-hidden /> : null}
      {!inAttempt ? "Not in this attempt" : blob.error ? "Image unavailable" : "Loading…"}
    </span>
  );
  return (
    <figure className="min-w-0" data-path={path}>
      {onOpen && inAttempt ? (
        <button
          type="button"
          onClick={() => onOpen(path)}
          aria-label={`Open ${caption ?? path}`}
          className="block aspect-square w-full overflow-hidden rounded-control border border-border bg-muted/20 hover:border-foreground/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          {picture}
        </button>
      ) : (
        <div
          title={path}
          className="aspect-square w-full overflow-hidden rounded-control border border-border bg-muted/20"
        >
          {picture}
        </div>
      )}
      <figcaption className="mt-1 min-w-0 text-micro text-muted-foreground">
        <span className="font-mono tabular-nums">{stepLabel(entry.step)}</span>
        {caption ? <span className="block truncate text-foreground">{caption}</span> : null}
      </figcaption>
    </figure>
  );
};

/** How many images a gallery shows before "show all": the latest ones. */
const IMAGE_LIMIT = 12;

export const ImageCard = ({
  card,
  coords,
  onOpenImage,
}: {
  card: MetricCard<ImageRef>;
  coords: AttemptCoords;
  onOpenImage?: (path: string) => void;
}): JSX.Element => {
  const [showAll, setShowAll] = useState(false);
  const hidden = showAll ? 0 : Math.max(0, card.entries.length - IMAGE_LIMIT);
  const shown = card.entries.slice(hidden);
  return (
    <CardFrame
      kind="image"
      title={card.key}
      meta={`${card.entries.length} ${card.entries.length === 1 ? "image" : "images"}`}
      replayedFrom={card.replayedFrom}
    >
      {hidden > 0 ? (
        <WorkbenchAction
          kind="ghost"
          size="compact"
          className="mb-1"
          onClick={() => setShowAll(true)}
        >
          Show {hidden} earlier
        </WorkbenchAction>
      ) : null}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(7rem,1fr))] gap-2">
        {shown.map((entry) => (
          <ImageThumb key={entry.order} coords={coords} entry={entry} onOpen={onOpenImage} />
        ))}
      </div>
    </CardFrame>
  );
};
