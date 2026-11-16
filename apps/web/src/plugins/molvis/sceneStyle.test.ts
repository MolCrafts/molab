import { describe, expect, it } from "@rstest/core";

import {
  BASE_FRAME_MS,
  colourByOptions,
  formatSpeed,
  frameIntervalMs,
  nextFrame,
  PLAYBACK_SPEEDS,
  speedStep,
} from "./sceneStyle";

describe("playback", () => {
  it("scales the stage's frame interval by the speed", () => {
    expect(frameIntervalMs(1)).toBe(BASE_FRAME_MS);
    expect(frameIntervalMs(2)).toBe(BASE_FRAME_MS / 2);
    expect(frameIntervalMs(0.25)).toBe(BASE_FRAME_MS * 4);
  });

  it("never divides by a non-positive speed", () => {
    expect(frameIntervalMs(0)).toBe(BASE_FRAME_MS);
    expect(frameIntervalMs(-1)).toBe(BASE_FRAME_MS);
  });

  it("maps a speed onto its slider step, 1× for anything off the ladder", () => {
    expect(speedStep(4)).toBe(PLAYBACK_SPEEDS.length - 1);
    expect(speedStep(3)).toBe(PLAYBACK_SPEEDS.indexOf(1));
    expect(formatSpeed(0.5)).toBe("0.5×");
  });

  it("loops the player back to the first frame", () => {
    expect(nextFrame(0, 12)).toBe(1);
    expect(nextFrame(11, 12)).toBe(0);
    expect(nextFrame(0, 0)).toBe(0);
  });
});

describe("colourByOptions", () => {
  it("offers the element palette for every structure", () => {
    expect(colourByOptions(["element", "x", "y", "z"])).toEqual([
      { value: "element", label: "Element" },
    ]);
  });

  it("offers the type column only when the structure has one", () => {
    expect(colourByOptions(["type", "x"]).map((option) => option.value)).toEqual([
      "element",
      "type",
    ]);
  });
});
