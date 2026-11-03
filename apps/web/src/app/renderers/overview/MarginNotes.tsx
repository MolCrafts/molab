// Margin notes for the Parameters tab — short, factual, each one a thing the
// reader would otherwise have to hunt for in the matrix.

import type { JSX } from "react";

import { Figure, Gauge } from "@/app/components/entity";

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
