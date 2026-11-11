/**
 * The MolVis style panel (L14): Representation (model, colour by, bonds),
 * View (projection, cell, axes), Playback (speed). Only what molvis-stage
 * carries out; the model list is the stage's own presets.
 */

import { RunView } from "@molcrafts/molab-plugin/ui";
import { NativeSelect, Slider } from "@molcrafts/ui";
import { SLIDER_CLASS } from "./FramePlayer";
import {
  type ColourBy,
  colourByOptions,
  formatSpeed,
  type MolvisStyle,
  PLAYBACK_SPEEDS,
  PROJECTION_OPTIONS,
  speedStep,
} from "./sceneStyle";
import type { SceneInfo } from "./TrajectoryViewer";

interface StylePanelProps {
  style: MolvisStyle;
  info: SceneInfo | null;
  /** A `setState`: each change merges into the latest style. */
  onChange: (update: (previous: MolvisStyle) => MolvisStyle) => void;
}

export const StylePanel = ({ style, info, onChange }: StylePanelProps): JSX.Element => {
  const set = <K extends keyof MolvisStyle>(key: K, value: MolvisStyle[K]): void =>
    onChange((previous) => ({ ...previous, [key]: value }));
  const models = info?.representations ?? [];
  const colours = colourByOptions(info?.columns ?? []);
  return (
    <>
      <RunView.StyleGroup title="Representation">
        <RunView.StyleRow label="Model">
          <NativeSelect
            aria-label="Model"
            sizeVariant="compact"
            className="w-full"
            disabled={models.length === 0}
            value={style.model}
            onChange={(event) => set("model", event.target.value)}
          >
            {models.length === 0 ? <option value={style.model}>{style.model}</option> : null}
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </NativeSelect>
        </RunView.StyleRow>
        <RunView.StyleRow label="Colour by">
          <NativeSelect
            aria-label="Colour by"
            sizeVariant="compact"
            className="w-full"
            disabled={colours.length < 2}
            value={
              colours.some((option) => option.value === style.colourBy) ? style.colourBy : "element"
            }
            onChange={(event) => set("colourBy", event.target.value as ColourBy)}
          >
            {colours.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </RunView.StyleRow>
        <RunView.StyleRow label="Bonds">
          <RunView.Switch
            label="Bonds"
            checked={style.bonds}
            onChange={(next) => set("bonds", next)}
          />
        </RunView.StyleRow>
      </RunView.StyleGroup>
      <RunView.StyleGroup title="View">
        <RunView.StyleRow label="Projection">
          <RunView.Choice
            label="Projection"
            value={style.projection}
            options={PROJECTION_OPTIONS}
            onChange={(next) => set("projection", next)}
          />
        </RunView.StyleRow>
        <RunView.StyleRow label="Cell">
          <RunView.Switch
            label="Cell"
            checked={style.cell}
            onChange={(next) => set("cell", next)}
          />
        </RunView.StyleRow>
        <RunView.StyleRow label="Axes">
          <RunView.Switch
            label="Axes"
            checked={style.axes}
            onChange={(next) => set("axes", next)}
          />
        </RunView.StyleRow>
      </RunView.StyleGroup>
      <RunView.StyleGroup title="Playback">
        <RunView.StyleRow label="Speed">
          <Slider
            className={SLIDER_CLASS}
            min={0}
            max={PLAYBACK_SPEEDS.length - 1}
            step={1}
            value={[speedStep(style.speed)]}
            thumbLabels={["Speed"]}
            onValueChange={([step]) => {
              const speed = step === undefined ? undefined : PLAYBACK_SPEEDS[step];
              if (speed !== undefined) set("speed", speed);
            }}
          />
          <span className="w-8 flex-none text-right font-mono text-label tabular-nums">
            {formatSpeed(style.speed)}
          </span>
        </RunView.StyleRow>
      </RunView.StyleGroup>
    </>
  );
};
