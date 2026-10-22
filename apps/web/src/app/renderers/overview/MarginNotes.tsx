// Margin notes for entity overviews — short, factual, each one a thing the
// reader would otherwise have to hunt for in the table below.

import { TriangleAlert } from "lucide-react";
import type { JSX } from "react";
import { Link } from "react-router-dom";

import { type DurationPoint, Figure, formatSpan, Gauge } from "@/app/components/entity";
import type { RunSummary } from "@/app/types";

import { runLabel } from "./gaugeData";

/** The newest failure and what it said. */
export const FailureNote = ({ run, href }: { run: RunSummary; href: string }): JSX.Element => (
  <Gauge title="Last failure">
    <Link
      to={href}
      className="group block min-w-0 rounded-control outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <span className="flex min-w-0 items-center gap-2">
        <TriangleAlert
          className="size-icon-sm shrink-0 text-status-failed-foreground"
          aria-hidden
        />
        <span className="min-w-0 truncate text-body font-medium text-foreground group-hover:underline">
          {runLabel(run)}
        </span>
      </span>
      {run.errorMessage ? (
        <span className="mt-2 line-clamp-4 block break-words font-mono text-label text-muted-foreground">
          {run.errorMessage}
        </span>
      ) : null}
    </Link>
  </Gauge>
);

/** Fastest and slowest finished run — the two ends of the strip, by name. */
export const ExtremesNote = ({
  points,
}: {
  points: readonly DurationPoint[];
}): JSX.Element | null => {
  if (points.length < 2) return null;
  const sorted = [...points].sort((left, right) => left.seconds - right.seconds);
  const ends = [
    { role: "Fastest", point: sorted[0] },
    { role: "Slowest", point: sorted[sorted.length - 1] },
  ];
  return (
    <Gauge title="Extremes">
      <dl className="space-y-3">
        {ends.map(({ role, point }) =>
          point ? (
            <div key={role} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4">
              <dt className="text-label text-muted-foreground">{role}</dt>
              <dd className="row-span-2 self-center font-mono text-body tabular-nums text-foreground">
                {formatSpan(point.seconds)}
              </dd>
              <dd className="min-w-0">
                {point.href ? (
                  <Link
                    to={point.href}
                    title={point.label}
                    className="block truncate text-body text-foreground hover:underline"
                  >
                    {point.label}
                  </Link>
                ) : (
                  <span className="block truncate text-body text-foreground">{point.label}</span>
                )}
              </dd>
            </div>
          ) : null,
        )}
      </dl>
    </Gauge>
  );
};

/** Parameters every run shares — said once, not on every row. */
export const ConstantsNote = ({
  constants,
}: {
  constants: readonly { key: string; value: string }[];
}): JSX.Element | null =>
  constants.length === 0 ? null : (
    <Gauge
      title="Held constant"
      readout={
        <>
          <Figure>{constants.length}</Figure> {constants.length === 1 ? "parameter" : "parameters"}
        </>
      }
    >
      <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-4 gap-y-2">
        {constants.map(({ key, value }) => (
          <div key={key} className="contents">
            <dt className="min-w-0 truncate font-mono text-label text-muted-foreground" title={key}>
              {key}
            </dt>
            <dd
              className="min-w-0 truncate text-right font-mono text-label text-foreground"
              title={value}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </Gauge>
  );

export interface AttentionLine {
  id: string;
  label: string;
  detail: string;
  tone: "failed" | "running" | "quiet";
  href: string;
}

const TONE_DOT: Record<AttentionLine["tone"], string> = {
  failed: "bg-status-failed",
  running: "bg-status-running mol-motion-progress-pulse",
  quiet: "bg-muted-foreground/50",
};

/** What in this scope wants a person: failures first, then live work, then gaps. */
export const AttentionNote = ({
  lines,
}: {
  lines: readonly AttentionLine[];
}): JSX.Element | null =>
  lines.length === 0 ? null : (
    <Gauge title="Wants attention" readout={<Figure>{lines.length}</Figure>}>
      <ul className="space-y-3">
        {lines.map((line) => (
          <li key={line.id}>
            <Link
              to={line.href}
              className="group grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-2 rounded-control outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <span
                aria-hidden
                className={`size-2 translate-y-px rounded-full ${TONE_DOT[line.tone]}`}
              />
              <span className="min-w-0 truncate text-body text-foreground group-hover:underline">
                {line.label}
              </span>
              <span />
              <span className="text-label text-muted-foreground">{line.detail}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Gauge>
  );
