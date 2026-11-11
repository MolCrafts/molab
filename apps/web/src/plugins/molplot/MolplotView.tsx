/**
 * MolPlot's run view (L14 v6): files | one figure | style.
 *
 * Files (left) — the attempt's files MolPlot reads, each checkable in its
 * legend colour. Figure (centre) — every series of every checked file and the
 * run's own Vega-Lite figures, as panels; Group by at its top right, the
 * legend beside it. Style (right, closable) — lines, axes, numbers, data.
 * There are no tabs, toolbars or summary lines.
 */

import type { RunViewProps } from "@molcrafts/molab-plugin";
import { RunView } from "@molcrafts/molab-plugin/ui";
import { ChartLine, FileText, Group } from "lucide-react";
import { type JSX, useCallback, useMemo, useState } from "react";
import { formatBytes } from "@/lib/format-bytes";
import { GROUP_BY_OPTIONS, type GroupBy } from "./figure-model";
import { FigurePanel, Legend, SeriesPanel } from "./MolplotPanels";
import { MolplotStylePanel } from "./MolplotStyle";
import { DEFAULT_STYLE, type MolplotStyle } from "./panel-data";
import { type MolplotFigure, useMolplotFigure, type ViewFile } from "./use-molplot-figure";

const fileItem = (file: ViewFile, unchecked: ReadonlySet<string>) => ({
  id: file.path,
  label: file.label,
  meta: file.error ? "unreadable" : file.size === null ? undefined : formatBytes(file.size),
  color: file.color,
  checked: !unchecked.has(file.path),
  icon: file.figure ? (
    <ChartLine className="size-icon-sm" aria-hidden />
  ) : (
    <FileText className="size-icon-sm" aria-hidden />
  ),
});

const Figure = ({ figure }: { figure: MolplotFigure }): JSX.Element => {
  const wide = figure.panels.length + figure.figures.length === 1;
  const panels = [
    ...figure.panels.map((panel) => (
      <SeriesPanel key={panel.id} panel={panel} style={figure.drawn} wide={wide} />
    )),
    ...figure.figures.map((file) => (
      <FigurePanel key={file.path} path={file.path} color={file.color} wide={wide} />
    )),
  ];
  return wide ? (
    <div className="flex flex-col">{panels}</div>
  ) : (
    <RunView.Grid>{panels}</RunView.Grid>
  );
};

const useToggleSet = (): [ReadonlySet<string>, (id: string) => void] => {
  const [set, setSet] = useState<ReadonlySet<string>>(() => new Set());
  const toggle = useCallback((id: string) => {
    setSet((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  return [set, toggle];
};

export const MolplotView = ({ attempt, files: matched }: RunViewProps): JSX.Element => {
  const [style, setStyle] = useState<MolplotStyle>(DEFAULT_STYLE);
  const [groupBy, setGroupBy] = useState<GroupBy>("quantity");
  const [unchecked, toggleFile] = useToggleSet();
  const figure = useMolplotFigure(attempt, matched, style, groupBy, unchecked);
  const patchStyle = useCallback(
    (patch: Partial<MolplotStyle>) => setStyle((current) => ({ ...current, ...patch })),
    [],
  );
  const items = useMemo(
    () => figure.files.map((file) => fileItem(file, unchecked)),
    [figure.files, unchecked],
  );

  const files = <RunView.Files items={items} mode="check" onToggle={toggleFile} />;
  const stylePanel = (
    <MolplotStylePanel
      style={figure.drawn}
      onChange={patchStyle}
      tasks={figure.tasks}
      timed={figure.timed}
    />
  );
  const groupMenu = (
    <RunView.Menu
      label="Group by"
      icon={<Group className="size-4" aria-hidden />}
      value={groupBy}
      options={GROUP_BY_OPTIONS}
      onChange={setGroupBy}
    />
  );

  return (
    <RunView
      files={files}
      header={figure.state ? null : <Legend entries={figure.legend} />}
      actions={groupMenu}
      style={stylePanel}
      state={figure.state}
    >
      <Figure figure={figure} />
    </RunView>
  );
};
