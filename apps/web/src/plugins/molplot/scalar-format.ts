/**
 * Display formatting for one-shot scalar metric values.
 *
 * ``auto`` picks scientific notation for large / tiny magnitudes (the
 * previous default). ``scientific`` always uses exponential form.
 * ``decimal`` uses ``toPrecision`` so the digit count is significant
 * figures, not a fixed decimal place.
 */

export type ScalarNotation = "auto" | "scientific" | "decimal";

export interface ScalarFormat {
  notation: ScalarNotation;
  /** Significant digits, 1–8. */
  significantDigits: number;
}

export const DEFAULT_SCALAR_FORMAT: ScalarFormat = {
  notation: "auto",
  significantDigits: 4,
};

const clampDigits = (digits: number): number => Math.min(8, Math.max(1, Math.round(digits)));

export const formatScalar = (
  value: number,
  format: ScalarFormat = DEFAULT_SCALAR_FORMAT,
): string => {
  if (!Number.isFinite(value)) return String(value);
  const digits = clampDigits(format.significantDigits);
  const expDigits = Math.max(0, digits - 1);
  if (format.notation === "scientific") {
    return value.toExponential(expDigits);
  }
  if (format.notation === "decimal") {
    return value.toPrecision(digits);
  }
  if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) {
    return value.toExponential(expDigits);
  }
  return value.toPrecision(digits);
};
