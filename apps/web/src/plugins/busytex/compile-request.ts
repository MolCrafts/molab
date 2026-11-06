/** Main file the engine turns into `main.pdf`. BusyTeX slices on the `.tex` suffix. */
export const MAIN_TEX_PATH = "main.tex";

/**
 * On-demand TeX Live 2026. Files missing from the preloaded basic set are
 * fetched once by name and kept by the engine. A TeX Live install on the
 * host is not visible to this browser engine.
 */
export const TEXLIVE_REMOTE_ENDPOINT = "https://texlive2026.texlyre.org";

export type TexInputFile = {
  path: string;
  content: string | Uint8Array;
};

export type TexCompileRequest = {
  input: string;
  mainTexPath: string;
  bibtex: false;
  biber: false;
  makeindex: false;
  rerun: true;
  verbose: "silent";
  shellEscape: false;
  remoteEndpoint: string;
  additionalFiles: TexInputFile[];
};

/** One buffer, pdfLaTeX, no shell escape. Extra packages come from the remote endpoint. */
export const compileRequest = (
  source: string,
  additionalFiles: TexInputFile[] = [],
): TexCompileRequest => ({
  input: source,
  mainTexPath: MAIN_TEX_PATH,
  bibtex: false,
  biber: false,
  makeindex: false,
  rerun: true,
  verbose: "silent",
  shellEscape: false,
  remoteEndpoint: TEXLIVE_REMOTE_ENDPOINT,
  additionalFiles,
});
