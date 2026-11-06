/**
 * How finely molplot asks for a curve, in simulation steps.
 *
 * Stated in the data's own units rather than in rows: a view does not know
 * how many rows a file has, and a solver's thermo frequency changes between
 * restart blocks — a real run here writes every 576 to 1000 steps — so every
 * Nth *row* would sample one stretch more densely than another. A point every
 * 10 000 steps is uniform in simulation time however often the solver wrote.
 *
 * One constant for every view, so a run drawn alone and the same run drawn
 * beside others are sampled identically and can be compared.
 */
export const STEP_INTERVAL = 10_000;
