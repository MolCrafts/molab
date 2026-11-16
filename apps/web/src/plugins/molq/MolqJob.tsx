/**
 * The job (L14 Molq): the verdict line (in the view's top row), the lifetime
 * bar drawn from the times the record holds, and the submission facts.
 */

import { RunView } from "@molcrafts/molab-plugin/ui";
import type { JSX } from "react";
import type { ExecutionResponse } from "@/api/generated/models/ExecutionResponse";
import { formatSpan, StatusIcon } from "@/app/components/entity";
import { statusSpec, TONE_FILL, TONE_TEXT } from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";
import { jobSeconds, jobVerdict, type Lifetime, lifetime, submissionFacts } from "./job";

/** Status glyph + "Job 421337 on hpc-slurm". */
export const MolqVerdict = ({
  status,
  executor,
}: {
  status: string;
  executor: Record<string, string>;
}): JSX.Element => (
  <h2 className="flex min-w-0 items-center gap-2 text-body-lg font-semibold">
    <StatusIcon status={status} />
    <span className="truncate">{jobVerdict(executor)}</span>
  </h2>
);

/** The job's wall time, at the right of the verdict line; nothing when unknown. */
export const MolqDuration = ({
  record,
}: {
  record: ExecutionResponse | undefined;
}): JSX.Element | null => {
  const seconds = jobSeconds(record);
  return seconds === null ? null : (
    <span className="text-body tabular-nums">{formatSpan(seconds)}</span>
  );
};

const labelPlace = (fraction: number): string =>
  fraction <= 0.15 ? "" : fraction >= 0.85 ? "-translate-x-full" : "-translate-x-1/2";

const LifetimeBar = ({ value, status }: { value: Lifetime; status: string }): JSX.Element => {
  const tone = statusSpec(status).tone;
  return (
    <div className="flex flex-col gap-2 px-2">
      <div className="relative h-3">
        {value.segments.map((segment) => (
          <span
            key={`${segment.from}-${segment.to}`}
            className={cn(
              "absolute top-1 h-1 rounded-full",
              segment.kind === "run" ? TONE_FILL[tone] : "bg-border",
            )}
            style={{
              left: `${segment.from * 100}%`,
              width: `${(segment.to - segment.from) * 100}%`,
            }}
          />
        ))}
        {value.points.map((point) => (
          <span
            key={point.key}
            title={`${point.key} ${point.iso}`}
            className={cn(
              "absolute top-0 size-3 -translate-x-1/2 rounded-full border-2 border-current bg-background",
              point.key === "submitted" ? "text-muted-foreground" : TONE_TEXT[tone],
            )}
            style={{ left: `${point.fraction * 100}%` }}
          />
        ))}
      </div>
      {/* Under its marker where the bar is wide enough to read; a wrapped line where not. */}
      <div className="@container text-label text-muted-foreground">
        <div className="relative hidden h-4 @md:block">
          {value.labels.map((label) => (
            <span
              key={label.text}
              className={cn("absolute top-0 whitespace-nowrap", labelPlace(label.fraction))}
              style={{ left: `${label.fraction * 100}%` }}
            >
              {label.text}
            </span>
          ))}
        </div>
        <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 @md:hidden">
          {value.labels.map((label) => (
            <span key={label.text} className="whitespace-nowrap">
              {label.text}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

export const MolqJob = ({
  record,
  status,
  executor,
}: {
  record: ExecutionResponse | undefined;
  status: string;
  executor: Record<string, string>;
}): JSX.Element => {
  const value = lifetime(record);
  const facts = submissionFacts(executor);
  return (
    <div className="flex max-w-4xl flex-col gap-6 pt-4">
      {value.points.length > 0 ? (
        <section aria-label="Lifetime" className="flex flex-col gap-3">
          <h3 className="text-body font-semibold">Lifetime</h3>
          <LifetimeBar value={value} status={status} />
        </section>
      ) : null}
      {facts.length > 0 ? (
        <section aria-label="Submission" className="flex flex-col gap-2">
          <h3 className="text-body font-semibold">Submission</h3>
          <RunView.Facts rows={facts} />
        </section>
      ) : null}
    </div>
  );
};
