/**
 * The 36px frame player under a trajectory (L14 MolVis): step, play / pause,
 * a scrubber and the frame readout. Shown only when there is more than one
 * frame; the stage's own player stays off.
 */

import { RunView } from "@molcrafts/molab-plugin/ui";
import type { Molvis } from "@molcrafts/molvis-stage";
import { Slider } from "@molcrafts/ui";
import { Pause, Play, StepForward } from "lucide-react";
import { useEffect, useState } from "react";
import { frameIntervalMs, nextFrame } from "./sceneStyle";

/**
 * A slider that fills its row. The library's rail (`bg-input-bottom`) has no
 * token in this app, so the rail takes the border colour.
 */
export const SLIDER_CLASS = "min-w-0 flex-1 [&_[data-slot=slider-track]]:bg-border";

interface FrameState {
  index: number;
  length: number;
}

const readFrames = (app: Molvis): FrameState => ({
  index: app.system.trajectory.currentIndex,
  length: app.system.trajectory.indexedLength,
});

const useFrames = (app: Molvis): FrameState => {
  const [frames, setFrames] = useState<FrameState>(() => readFrames(app));
  useEffect(() => {
    const sync = (): void => setFrames(readFrames(app));
    const off = [
      app.events.on("frame-change", sync),
      app.events.on("length-changed", sync),
      app.events.on("trajectory-change", sync),
    ];
    sync();
    return () => {
      for (const unsubscribe of off) unsubscribe();
    };
  }, [app]);
  return frames;
};

export const FramePlayer = ({ app, speed }: { app: Molvis; speed: number }): JSX.Element | null => {
  const { index, length } = useFrames(app);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const { index: at, length: total } = readFrames(app);
      void app.seekFrame(nextFrame(at, total));
    }, frameIntervalMs(speed));
    return () => clearInterval(timer);
  }, [app, playing, speed]);

  if (length <= 1) return null;
  const step = (): void => {
    setPlaying(false);
    void app.seekFrame(nextFrame(index, length));
  };

  return (
    <div className="flex h-9 flex-none items-center gap-3 border-t border-border px-4">
      <RunView.IconButton label="Next frame" onClick={step}>
        <StepForward aria-hidden className="size-icon-sm" />
      </RunView.IconButton>
      <button
        type="button"
        aria-label={playing ? "Pause" : "Play"}
        title={playing ? "Pause" : "Play"}
        onClick={() => setPlaying((value) => !value)}
        className="inline-flex size-6 flex-none items-center justify-center rounded-control bg-accent text-accent-foreground hover:bg-accent-hover"
      >
        {playing ? (
          <Pause aria-hidden className="size-icon-sm" />
        ) : (
          <Play aria-hidden className="size-icon-sm" />
        )}
      </button>
      <Slider
        className={SLIDER_CLASS}
        min={0}
        max={length - 1}
        step={1}
        value={[index]}
        thumbLabels={["Frame"]}
        onValueChange={([next]) => {
          if (next !== undefined) void app.seekFrame(next);
        }}
      />
      <span className="flex-none font-mono text-label tabular-nums text-muted-foreground">
        {index + 1} / {length}
      </span>
    </div>
  );
};
