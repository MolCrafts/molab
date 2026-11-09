/**
 * The Runs filter view (Figma L05-1): the side bar of the Runs tab. Status (by
 * each run's latest attempt, in the vocabulary's words and glyphs), Project,
 * Experiment (once a project is picked), Target and Started. A facet's count
 * is how many runs picking it would show, so a pick and the table agree.
 */

import { ChevronDown, ChevronRight, RotateCcw } from "lucide-react";
import { type JSX, type ReactNode, useId, useMemo, useState } from "react";
import { StatusIcon } from "@/app/components/entity";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

import type { FacetCount, FacetSnapshot } from "./aggregates";
import {
  type ArrayFilterKey,
  hasActiveFilters,
  toggleArrayFilter,
  toggleStarted,
} from "./filterParams";
import type { RunsStartedWindow, WorkspaceRunsFilters } from "./types";

interface RunsFacetPanelProps {
  facets: FacetSnapshot;
  filters: WorkspaceRunsFilters;
  onFiltersChange: (next: WorkspaceRunsFilters) => void;
}

const STARTED: readonly { id: RunsStartedWindow; label: string }[] = [
  { id: "24h", label: "Last 24 hours" },
  { id: "7d", label: "Last 7 days" },
];

/** Values shown per facet before “n more”. */
const COLLAPSE_THRESHOLD = 8;

/** A section of the filter view: a 22px caps header that folds, VS Code style. */
const Section = ({ title, children }: { title: string; children: ReactNode }): JSX.Element => {
  const [open, setOpen] = useState(true);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <section aria-label={title}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-shell-crumbs w-full items-center gap-1 px-1 text-micro font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring"
      >
        <Chevron aria-hidden className="size-icon-sm" />
        {title}
      </button>
      {open ? <ul className="pb-2">{children}</ul> : null}
    </section>
  );
};

const Row = ({
  label,
  lead,
  count,
  checked,
  onToggle,
}: {
  label: string;
  lead?: ReactNode;
  count: number;
  checked: boolean;
  onToggle: () => void;
}): JSX.Element => {
  const id = useId();
  const dimmed = count === 0 && !checked;
  return (
    <li
      className={cn(
        "flex h-6 items-center gap-2 rounded-hairline pr-2 pl-6 text-body hover:bg-interactive",
        dimmed && "opacity-50",
      )}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="size-3.5 shrink-0 accent-accent"
      />
      {lead}
      <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer truncate">
        {label}
      </label>
      <span className="shrink-0 text-label tabular-nums text-muted-foreground">{count}</span>
    </li>
  );
};

const FacetSection = ({
  title,
  facetKey,
  options,
  filters,
  onFiltersChange,
  glyphs = false,
}: {
  title: string;
  facetKey: ArrayFilterKey;
  options: FacetCount[];
  filters: WorkspaceRunsFilters;
  onFiltersChange: (next: WorkspaceRunsFilters) => void;
  /** Status values: draw each with its glyph. */
  glyphs?: boolean;
}): JSX.Element | null => {
  const [expanded, setExpanded] = useState(false);
  const selected = useMemo(() => new Set(filters[facetKey] ?? []), [filters, facetKey]);
  // A picked value that no longer has runs stays listed (at 0) so it can be unpicked.
  const merged = useMemo(() => {
    const listed = new Set(options.map((option) => option.value));
    return [
      ...options,
      ...[...selected]
        .filter((value) => !listed.has(value))
        .map((value) => ({ value, label: value, count: 0 })),
    ];
  }, [options, selected]);
  if (merged.length === 0) return null;
  const visible = expanded ? merged : merged.slice(0, COLLAPSE_THRESHOLD);
  return (
    <Section title={title}>
      {visible.map((option) => (
        <Row
          key={option.value}
          label={option.label}
          lead={
            glyphs ? (
              <StatusIcon status={option.value} className="size-icon-sm shrink-0" />
            ) : undefined
          }
          count={option.count}
          checked={selected.has(option.value)}
          onToggle={() => onFiltersChange(toggleArrayFilter(filters, facetKey, option.value))}
        />
      ))}
      {merged.length > COLLAPSE_THRESHOLD ? (
        <li>
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="h-6 pl-12 text-label text-muted-foreground hover:text-foreground"
          >
            {expanded ? "Fewer" : `${merged.length - COLLAPSE_THRESHOLD} more`}
          </button>
        </li>
      ) : null}
    </Section>
  );
};

export const RunsFacetPanel = ({
  facets,
  filters,
  onFiltersChange,
}: RunsFacetPanelProps): JSX.Element => (
  <div className="space-y-1">
    <FacetSection
      title="Status"
      facetKey="status"
      options={facets.status}
      filters={filters}
      onFiltersChange={onFiltersChange}
      glyphs
    />
    <FacetSection
      title="Project"
      facetKey="projectId"
      options={facets.projectId}
      filters={filters}
      onFiltersChange={onFiltersChange}
    />
    {(filters.projectId?.length ?? 0) > 0 ? (
      <FacetSection
        title="Experiment"
        facetKey="experimentId"
        options={facets.experimentId}
        filters={filters}
        onFiltersChange={onFiltersChange}
      />
    ) : null}
    <FacetSection
      title="Target"
      facetKey="target"
      options={facets.target}
      filters={filters}
      onFiltersChange={onFiltersChange}
    />
    <Section title="Started">
      {STARTED.map((window) => (
        <Row
          key={window.id}
          label={window.label}
          count={facets.started[window.id]}
          checked={filters.started?.includes(window.id) ?? false}
          onToggle={() => onFiltersChange(toggleStarted(filters, window.id))}
        />
      ))}
    </Section>
    {hasActiveFilters(filters) ? (
      <div className="pl-4">
        <WorkbenchIconAction label="Clear all filters" onClick={() => onFiltersChange({})}>
          <RotateCcw aria-hidden className="size-icon-sm" />
        </WorkbenchIconAction>
      </div>
    ) : null}
  </div>
);
