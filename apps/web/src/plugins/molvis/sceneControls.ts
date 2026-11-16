/**
 * Drive a mounted molvis-stage app from the run view's style.
 *
 * The run view draws its own chrome (files, style, frame player), so the stage
 * mounts with none of its own: no info / FPS / view / mode panels, no status
 * line, no player. Every call here goes through the stage's public surface.
 */

import type { Molvis } from "@molcrafts/molvis-stage";
import type { MolvisCore } from "./loadMolvisCore";
import type { MolvisStyle, Projection } from "./sceneStyle";

/** The stage's chrome stays off: the run view owns every control on screen. */
export const SCENE_CONFIG = { showUI: false } as const;

/** The pipeline entry the run view's Colour by adds. */
export const COLOUR_BY_ENTRY = "molab-colour-by";

type ColumnFrame = { has(name: string): boolean; get(name: string): { keys(): string[] } };

/** The atom columns of the loaded frame (empty before a load). */
export const atomColumns = (app: Molvis): string[] => {
  const frame = app.frame as unknown as ColumnFrame | null;
  if (!frame?.has("atoms")) return [];
  return [...frame.get("atoms").keys()];
};

/**
 * Representation, bonds, cell and colour in one pipeline pass. A preset's
 * bonds stay as the preset draws them; Bonds off hides them in every preset.
 */
export const applyPipelineStyle = async (
  app: Molvis,
  core: Pick<MolvisCore, "findRepresentation" | "ColorByPropertyModifier">,
  style: Pick<MolvisStyle, "model" | "bonds" | "cell" | "colourBy">,
): Promise<void> => {
  const preset = core.findRepresentation(
    style.model as Parameters<typeof core.findRepresentation>[0],
  );
  app.styleManager.setRepresentation(style.bonds ? preset : { ...preset, showBonds: false });
  app.styleManager.setShowBox(style.cell);
  app.modifierPipeline.removeEntry(COLOUR_BY_ENTRY);
  if (style.colourBy !== "element" && atomColumns(app).includes(style.colourBy)) {
    const colour = new core.ColorByPropertyModifier(COLOUR_BY_ENTRY);
    colour.columnName = style.colourBy;
    colour.categorical = true;
    app.modifierPipeline.addModifier(colour);
  }
  if (app.frame) await app.applyPipeline({ fullRebuild: true });
};

/** Orthographic keeps the perspective view's framing at the target distance. */
export const applyProjection = (app: Molvis, projection: Projection): void => {
  const { camera } = app.world;
  if (projection === "orthographic") {
    const height = 2 * camera.radius * Math.tan(camera.fov / 2);
    const width = height * app.world.scene.getEngine().getAspectRatio(camera);
    camera.orthoTop = height / 2;
    camera.orthoBottom = -height / 2;
    camera.orthoLeft = -width / 2;
    camera.orthoRight = width / 2;
  } else {
    camera.orthoTop = null;
    camera.orthoBottom = null;
    camera.orthoLeft = null;
    camera.orthoRight = null;
  }
  app.world.viewportSettings.setPerspective(projection === "perspective");
  app.world.renderOnce();
};

type AxisHelper = NonNullable<Molvis["world"]["axisHelper"]>;
const parkedAxes = new WeakMap<Molvis, AxisHelper>();

/**
 * Show or hide the corner axis helper. The stage builds it once at mount and
 * renders whatever `world.axisHelper` holds, so hiding parks it and showing
 * puts it back (restore before `destroy`, which disposes it).
 */
export const applyAxes = (app: Molvis, show: boolean): void => {
  const { world } = app;
  if (!show && world.axisHelper) {
    parkedAxes.set(app, world.axisHelper);
    world.axisHelper = undefined;
  } else if (show && !world.axisHelper) {
    world.axisHelper = parkedAxes.get(app);
    parkedAxes.delete(app);
  }
  world.renderOnce();
};

/** Paint the canvas the page ground (`#RRGGBB`). */
export const applyGround = (app: Molvis, ground: string | null): void => {
  if (ground) app.setBackgroundColor(ground);
};
