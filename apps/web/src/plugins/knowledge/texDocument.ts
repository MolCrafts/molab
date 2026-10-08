/** A knowledge-listed TeX manuscript. Suffixes match the BusyTeX preview. */

const TEX_SUFFIXES = [".tex", ".ltx"] as const;

export const isTexDocument = (path: string): boolean => {
  const lower = path.toLowerCase();
  return TEX_SUFFIXES.some((suffix) => lower.endsWith(suffix));
};
