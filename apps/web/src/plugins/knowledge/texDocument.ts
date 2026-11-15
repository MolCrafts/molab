/** A Manuscript's LaTeX file. Suffixes match the BusyTeX preview. */

const TEX_SUFFIXES = [".tex", ".ltx"] as const;

export const isTexDocument = (path: string): boolean => {
  const lower = path.toLowerCase();
  return TEX_SUFFIXES.some((suffix) => lower.endsWith(suffix));
};

/** A live (uncommented) `\\bibliography{name}` and the first file it names. */
const BIBLIOGRAPHY = /^[^%\n]*\\bibliography\{\s*([^},\s]+)/m;

/** The bibliography file a LaTeX source names with `\\bibliography{name}`, or `null`. */
export const bibliographyName = (source: string): string | null =>
  BIBLIOGRAPHY.exec(source)?.[1] ?? null;

/**
 * *source* with *bibtex* prepended as the file its `\\bibliography` names, in a
 * `filecontents*` block, so the one buffer a preview compiles carries the
 * bibliography molab writes from the cited Literature. A source that names no
 * bibliography is returned unchanged.
 */
export const withBibliography = (source: string, bibtex: string): string => {
  const name = bibliographyName(source);
  if (name === null) return source;
  const file = name.endsWith(".bib") ? name : `${name}.bib`;
  return `\\begin{filecontents*}[overwrite]{${file}}\n${bibtex}\n\\end{filecontents*}\n${source}`;
};
