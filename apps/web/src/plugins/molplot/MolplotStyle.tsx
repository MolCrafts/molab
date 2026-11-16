/**
 * MolPlot's Style panel (L14): Lines, Axes, Numbers and Data, composed from
 * the run-view SDK's groups, rows, choices and switch. The SDK has no slider,
 * number field or select, so those come from the app's own controls.
 */

import { RunView } from "@molcrafts/molab-plugin/ui";
import {
  NumberField,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Slider,
} from "@molcrafts/ui";
import type { JSX } from "react";
import type { MolplotStyle, XAxis, YAxis } from "./panel-data";
import type { ScalarNotation } from "./scalar-format";

const ALL_TASKS = "\u0000all";

const RAW_OPTIONS = [
  { value: "show", label: "Show" },
  { value: "hide", label: "Hide" },
] as const;
const X_OPTIONS: readonly { value: XAxis; label: string }[] = [
  { value: "step", label: "Step" },
  { value: "time", label: "Time" },
];
const Y_OPTIONS: readonly { value: YAxis; label: string }[] = [
  { value: "linear", label: "Linear" },
  { value: "log", label: "Log" },
];
const NOTATIONS: readonly { value: ScalarNotation; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "scientific", label: "Scientific" },
  { value: "decimal", label: "Decimal" },
];

interface StyleProps {
  style: MolplotStyle;
  onChange: (patch: Partial<MolplotStyle>) => void;
  /** Tasks the records name; the Data group shows only when there are some. */
  tasks: readonly string[];
  /** Some series measured a wall clock, so a Time axis can draw it. */
  timed: boolean;
}

const SliderValue = ({ children }: { children: string }): JSX.Element => (
  <span className="w-8 flex-none text-right font-mono text-label tabular-nums">{children}</span>
);

const LinesGroup = ({ style, onChange }: StyleProps): JSX.Element => (
  <RunView.StyleGroup title="Lines">
    <RunView.StyleRow label="Smoothing">
      <Slider
        min={0}
        max={0.99}
        step={0.01}
        value={[style.smoothing]}
        onValueChange={([value]) => onChange({ smoothing: value ?? 0 })}
        thumbLabels={["Smoothing"]}
        className="min-w-0 flex-1"
      />
      <SliderValue>{style.smoothing.toFixed(2)}</SliderValue>
    </RunView.StyleRow>
    <RunView.StyleRow label="Raw">
      <RunView.Choice
        label="Raw"
        value={style.raw ? "show" : "hide"}
        options={RAW_OPTIONS}
        onChange={(value) => onChange({ raw: value === "show" })}
      />
    </RunView.StyleRow>
    <RunView.StyleRow label="Spike filter">
      <RunView.Switch
        label="Spike filter"
        checked={style.spikeFilter}
        onChange={(spikeFilter) => onChange({ spikeFilter })}
      />
      {style.spikeFilter ? (
        <>
          <NumberField
            aria-label="Spike threshold in sigma"
            value={style.spikeSigma}
            min={2}
            max={8}
            step={0.5}
            onChange={(spikeSigma) => onChange({ spikeSigma })}
            className="h-shell-action w-12 px-2 font-mono text-label"
          />
          <span className="text-label text-muted-foreground">σ</span>
        </>
      ) : null}
    </RunView.StyleRow>
  </RunView.StyleGroup>
);

const AxesGroup = ({ style, onChange, timed }: StyleProps): JSX.Element => (
  <RunView.StyleGroup title="Axes">
    {timed ? (
      <RunView.StyleRow label="X">
        <RunView.Choice
          label="X axis"
          value={style.x}
          options={X_OPTIONS}
          onChange={(x) => onChange({ x })}
        />
      </RunView.StyleRow>
    ) : null}
    <RunView.StyleRow label="Y">
      <RunView.Choice
        label="Y axis"
        value={style.y}
        options={Y_OPTIONS}
        onChange={(y) => onChange({ y })}
      />
    </RunView.StyleRow>
  </RunView.StyleGroup>
);

const NumbersGroup = ({ style, onChange }: StyleProps): JSX.Element => (
  <RunView.StyleGroup title="Numbers">
    <RunView.StyleRow label="Notation">
      <Select
        value={style.notation}
        onValueChange={(value) => onChange({ notation: value as ScalarNotation })}
      >
        <SelectTrigger aria-label="Notation" className="h-control-compact min-w-0 flex-1">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {NOTATIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </RunView.StyleRow>
    <RunView.StyleRow label="Digits">
      <Slider
        min={1}
        max={8}
        step={1}
        value={[style.digits]}
        onValueChange={([value]) => onChange({ digits: value ?? style.digits })}
        thumbLabels={["Significant digits"]}
        className="min-w-0 flex-1"
      />
      <SliderValue>{String(style.digits)}</SliderValue>
    </RunView.StyleRow>
  </RunView.StyleGroup>
);

const DataGroup = ({ style, onChange, tasks }: StyleProps): JSX.Element => (
  <RunView.StyleGroup title="Data">
    <RunView.StyleRow label="Task">
      <Select
        value={style.task ?? ALL_TASKS}
        onValueChange={(value) => onChange({ task: value === ALL_TASKS ? null : value })}
      >
        <SelectTrigger aria-label="Task" className="h-control-compact min-w-0 flex-1">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_TASKS}>All tasks</SelectItem>
          {tasks.map((task) => (
            <SelectItem key={task} value={task}>
              {task}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </RunView.StyleRow>
  </RunView.StyleGroup>
);

/** The Style panel's content. */
export const MolplotStylePanel = (props: StyleProps): JSX.Element => (
  <>
    <LinesGroup {...props} />
    <AxesGroup {...props} />
    <NumbersGroup {...props} />
    {props.tasks.length > 0 ? <DataGroup {...props} /> : null}
  </>
);
