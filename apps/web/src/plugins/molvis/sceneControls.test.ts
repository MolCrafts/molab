import type { Molvis } from "@molcrafts/molvis-stage";
import { describe, expect, it } from "@rstest/core";

import {
  applyAxes,
  applyPipelineStyle,
  applyProjection,
  atomColumns,
  COLOUR_BY_ENTRY,
} from "./sceneControls";

interface Fake {
  app: Molvis;
  calls: string[];
  camera: Record<string, number | null>;
  world: { axisHelper?: object; perspective: boolean | null; renders: number };
  representation: { id: string; showBonds: boolean } | null;
  showBox: boolean | null;
  modifiers: { id: string; columnName?: string; categorical?: boolean }[];
}

const fakeApp = (columns: string[] | null): Fake => {
  const fake: Fake = {
    app: null as unknown as Molvis,
    calls: [],
    camera: {
      radius: 10,
      fov: Math.PI / 2,
      orthoTop: null,
      orthoBottom: null,
      orthoLeft: null,
      orthoRight: null,
    },
    world: { axisHelper: { name: "axes" }, perspective: null, renders: 0 },
    representation: null,
    showBox: null,
    modifiers: [],
  };
  const world = {
    camera: fake.camera,
    get axisHelper() {
      return fake.world.axisHelper;
    },
    set axisHelper(value: object | undefined) {
      fake.world.axisHelper = value;
    },
    scene: { getEngine: () => ({ getAspectRatio: () => 2 }) },
    viewportSettings: {
      setPerspective: (value: boolean) => {
        fake.world.perspective = value;
      },
    },
    renderOnce: () => {
      fake.world.renders += 1;
    },
  };
  fake.app = {
    world,
    frame: columns
      ? { has: (name: string) => name === "atoms", get: () => ({ keys: () => columns }) }
      : null,
    styleManager: {
      setRepresentation: (value: { id: string; showBonds: boolean }) => {
        fake.representation = value;
      },
      setShowBox: (value: boolean) => {
        fake.showBox = value;
      },
    },
    modifierPipeline: {
      removeEntry: (id: string) => {
        fake.modifiers = fake.modifiers.filter((entry) => entry.id !== id);
        return [];
      },
      addModifier: (entry: { id: string }) => {
        fake.modifiers = [...fake.modifiers, entry];
      },
    },
    applyPipeline: async () => {
      fake.calls.push("applyPipeline");
      return null;
    },
  } as unknown as Molvis;
  return fake;
};

class FakeColour {
  columnName = "";
  categorical = false;
  constructor(public id: string) {}
}

const core = {
  findRepresentation: (id: string) => ({ id, showBonds: true }),
  ColorByPropertyModifier: FakeColour,
} as unknown as Parameters<typeof applyPipelineStyle>[1];

const style = { model: "spacefill", bonds: true, cell: true, colourBy: "element" as const };

describe("applyPipelineStyle", () => {
  it("applies the preset, the cell and one pipeline pass", async () => {
    const fake = fakeApp(["element", "x"]);
    await applyPipelineStyle(fake.app, core, style);
    expect(fake.representation).toEqual({ id: "spacefill", showBonds: true });
    expect(fake.showBox).toBe(true);
    expect(fake.calls).toEqual(["applyPipeline"]);
  });

  it("hides the preset's bonds when Bonds is off", async () => {
    const fake = fakeApp(["element"]);
    await applyPipelineStyle(fake.app, core, { ...style, bonds: false, cell: false });
    expect(fake.representation?.showBonds).toBe(false);
    expect(fake.showBox).toBe(false);
  });

  it("colours by type only when the frame has the column, and never twice", async () => {
    const typed = fakeApp(["type"]);
    await applyPipelineStyle(typed.app, core, { ...style, colourBy: "type" });
    await applyPipelineStyle(typed.app, core, { ...style, colourBy: "type" });
    expect(typed.modifiers).toEqual([
      expect.objectContaining({ id: COLOUR_BY_ENTRY, columnName: "type", categorical: true }),
    ]);
    await applyPipelineStyle(typed.app, core, style);
    expect(typed.modifiers).toEqual([]);

    const untyped = fakeApp(["element"]);
    await applyPipelineStyle(untyped.app, core, { ...style, colourBy: "type" });
    expect(untyped.modifiers).toEqual([]);
  });

  it("skips the pipeline pass before a frame is loaded", async () => {
    const fake = fakeApp(null);
    await applyPipelineStyle(fake.app, core, style);
    expect(fake.calls).toEqual([]);
    expect(atomColumns(fake.app)).toEqual([]);
  });
});

describe("applyProjection", () => {
  it("frames orthographic like the perspective view and clears it again", () => {
    const fake = fakeApp(null);
    applyProjection(fake.app, "orthographic");
    expect(fake.world.perspective).toBe(false);
    expect(fake.camera.orthoTop).toBeCloseTo(10);
    expect(fake.camera.orthoRight).toBeCloseTo(20);
    applyProjection(fake.app, "perspective");
    expect(fake.world.perspective).toBe(true);
    expect(fake.camera.orthoTop).toBeNull();
  });
});

describe("applyAxes", () => {
  it("parks the axis helper and puts the same one back", () => {
    const fake = fakeApp(null);
    const helper = fake.world.axisHelper;
    applyAxes(fake.app, false);
    expect(fake.world.axisHelper).toBeUndefined();
    applyAxes(fake.app, false);
    applyAxes(fake.app, true);
    expect(fake.world.axisHelper).toBe(helper);
    expect(fake.world.renders).toBe(3);
  });
});
