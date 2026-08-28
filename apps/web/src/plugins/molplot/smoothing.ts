/**
 * TensorBoard-style exponential moving average with debias correction.
 *
 * weight ∈ [0, 1) controls smoothing strength: 0 = no smoothing (returns raw),
 * 0.6 (default) = mild, 0.9+ = aggressive. The debias term `1 - weight^k`
 * prevents the early-step pull toward zero that a naive EMA exhibits.
 */
export const smoothEma = (values: ReadonlyArray<number>, weight: number): number[] => {
  if (weight <= 0 || values.length === 0) {
    return values.slice();
  }
  const w = Math.min(weight, 0.999);
  const out = new Array<number>(values.length);
  let last = 0;
  let debiasWeight = 0;
  for (let i = 0; i < values.length; i += 1) {
    const v = values[i];
    if (!Number.isFinite(v)) {
      out[i] = Number.NaN;
      continue;
    }
    last = last * w + (1 - w) * v;
    debiasWeight = debiasWeight * w + (1 - w);
    out[i] = last / debiasWeight;
  }
  return out;
};

const DEFAULT_SPIKE_WINDOW = 21;
const DEFAULT_SPIKE_SIGMA = 4;
/** Consistency constant: MAD → σ for a Gaussian. */
const MAD_TO_SIGMA = 1.4826;
const MIN_SPIKE_HISTORY = 5;

export interface SpikeFilterOptions {
  /** Causal look-behind length in previous points. Default 21. */
  window?: number;
  /** Modified-Z threshold in σ units. Default 4. Lower = more aggressive. */
  nSigma?: number;
}

const medianOf = (values: number[]): number => {
  const sorted = values.slice().sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/**
 * Causal Hampel / MAD spike filter.
 *
 * Each point is compared to the median of the preceding `window` already-
 * cleaned values. If it sits more than `nSigma` robust σ away, it is replaced
 * with that median. Look-behind (not a centered window) so a streaming append
 * at t never rewrites t-1.
 *
 * Apply this *before* {@link smoothEma}: a single glitch must not yank the
 * smoothed curve.
 */
export const filterSpikes = (
  values: ReadonlyArray<number>,
  options: SpikeFilterOptions = {},
): number[] => {
  const window = Math.max(MIN_SPIKE_HISTORY, options.window ?? DEFAULT_SPIKE_WINDOW);
  const nSigma = options.nSigma ?? DEFAULT_SPIKE_SIGMA;
  const out = values.slice();

  for (let i = 0; i < values.length; i += 1) {
    const v = values[i];
    if (!Number.isFinite(v)) {
      out[i] = Number.NaN;
      continue;
    }
    const start = Math.max(0, i - window);
    const hist: number[] = [];
    for (let j = start; j < i; j += 1) {
      const h = out[j];
      if (Number.isFinite(h)) hist.push(h);
    }
    if (hist.length < MIN_SPIKE_HISTORY) {
      out[i] = v;
      continue;
    }
    const med = medianOf(hist);
    const mad = medianOf(hist.map((x) => Math.abs(x - med)));
    const floor = Math.max(Math.abs(med) * 0.005, 1e-12);
    const sigma = Math.max(MAD_TO_SIGMA * mad, floor);
    out[i] = Math.abs(v - med) > nSigma * sigma ? med : v;
  }
  return out;
};
