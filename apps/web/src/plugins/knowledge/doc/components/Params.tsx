/**
 * `<molab-params run=…>` (L10): a parameter set, as code. With `run` it is that
 * run's parameters; without, every other attribute is a row
 * (`::molab-params{ensemble="nve, nvt" steps=500}`).
 */

import { SlidersHorizontal } from "lucide-react";
import type { JSX } from "react";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentFrame, ComponentNotice } from "../frame";
import { useDocRun } from "./docRuns";
import { formatCell } from "./runQuery";

const NAME = "molab-params";

interface ParamRow {
  key: string;
  value: string;
}

const ParamList = ({ rows, label }: { rows: readonly ParamRow[]; label: string }): JSX.Element => (
  <ComponentFrame label={label}>
    <dl className="divide-y divide-border">
      {rows.map((row) => (
        <div key={row.key} className="flex h-shell-button items-center gap-4 px-3 font-mono">
          <dt className="w-44 flex-none truncate text-muted-foreground" title={row.key}>
            {row.key}
          </dt>
          <dd className="min-w-0 truncate text-foreground" title={row.value}>
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  </ComponentFrame>
);

const RunParams = ({ refText }: { refText: string }): JSX.Element => {
  const run = useDocRun(refText);
  if (!run) return <ComponentNotice name={NAME}>{refText} does not resolve.</ComponentNotice>;
  const rows = Object.entries(run.parameters ?? {}).map(([key, value]) => ({
    key,
    value: formatCell(value).text,
  }));
  if (rows.length === 0) {
    return <ComponentNotice name={NAME}>This run has no parameters.</ComponentNotice>;
  }
  return <ParamList rows={rows} label={`Parameters of ${run.title || run.name || run.id}`} />;
};

export const Params = ({ attrs }: DocComponentProps): JSX.Element => {
  if (attrs.run) return <RunParams refText={attrs.run} />;
  const rows = Object.entries(attrs).map(([key, value]) => ({ key, value }));
  if (rows.length === 0) {
    return (
      <ComponentNotice name={NAME}>
        Needs run=molab:run/… or one attribute per parameter.
      </ComponentNotice>
    );
  }
  return <ParamList rows={rows} label="Parameters" />;
};

export const paramsSpec: DocComponentSpec = {
  name: NAME,
  label: "Parameters",
  description: "A parameter set as code: a run's parameters, or the ones written here",
  keywords: ["params", "parameters", "config", "settings", "run"],
  icon: SlidersHorizontal,
  template: { run: "molab:run/" },
  Component: Params,
};
