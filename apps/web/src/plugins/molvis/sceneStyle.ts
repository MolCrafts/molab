/**
 * The style a MolVis run view applies to its scene (L14 · Style panel).
 *
 * Every setting here is one molvis-stage can carry out: a representation
 * preset, the bonds of that preset, colour by a categorical atom column, the
 * camera projection, the cell wireframe, the corner axis helper, and the
 * playback rate of the frame player.
 */

export type Projection = "perspective" | "orthographic";

/** `element` is the stage's element palette; any other value is an atom column. */
export type ColourBy = "element" | "type";

export interface MolvisStyle {
  /** A molvis-stage `RepresentationId`. */
  model: string;
  colourBy: ColourBy;
  bonds: boolean;
  projection: Projection;
  cell: boolean;
  axes: boolean;
  /** Playback rate, a multiple of {@link BASE_FRAME_MS}. */
  speed: number;
}

export const DEFAULT_STYLE: MolvisStyle = {
  model: "ball-and-stick",
  colourBy: "element",
  bonds: true,
  projection: "perspective",
  cell: true,
  axes: true,
  speed: 1,
};

/** One frame per 100 ms at 1×: the stage's own player rate. */
export const BASE_FRAME_MS = 100;

export const PLAYBACK_SPEEDS = [0.25, 0.5, 1, 2, 4] as const;

export const frameIntervalMs = (speed: number): number => BASE_FRAME_MS / (speed > 0 ? speed : 1);

export const formatSpeed = (speed: number): string => `${speed}×`;

/** The index of *speed* on {@link PLAYBACK_SPEEDS} (1× when it is not one). */
export const speedStep = (speed: number): number => {
  const index = PLAYBACK_SPEEDS.indexOf(speed as (typeof PLAYBACK_SPEEDS)[number]);
  return index < 0 ? PLAYBACK_SPEEDS.indexOf(1) : index;
};

export const PROJECTION_OPTIONS: readonly { value: Projection; label: string }[] = [
  { value: "perspective", label: "Persp" },
  { value: "orthographic", label: "Ortho" },
];

const COLOUR_BY_LABEL: Record<ColourBy, string> = { element: "Element", type: "Type" };

/**
 * What the loaded structure can be coloured by: the element palette always,
 * and its atom `type` column when it has one.
 */
export const colourByOptions = (
  atomColumns: readonly string[],
): { value: ColourBy; label: string }[] => [
  { value: "element", label: COLOUR_BY_LABEL.element },
  ...(atomColumns.includes("type")
    ? [{ value: "type" as const, label: COLOUR_BY_LABEL.type }]
    : []),
];

/** The next frame of a looping player. */
export const nextFrame = (index: number, length: number): number =>
  length <= 0 ? 0 : index >= length - 1 ? 0 : index + 1;
