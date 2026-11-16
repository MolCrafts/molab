import { BusyTexRunner, PdfLatex } from "texlyre-busytex";
import { compileRequest, type TexInputFile } from "./compile-request";

/** Same-origin assets from `public/busytex/`. Installed once; the browser caches them. */
export const BUSYTEX_BASE_PATH = "/busytex";

const PRELOAD_DATA_PACKAGE = `${BUSYTEX_BASE_PATH}/texlive-basic.js`;

export type CompileResult = {
  pdf: Uint8Array | null;
  log: string;
};

let runnerPromise: Promise<BusyTexRunner> | null = null;
let queue: Promise<unknown> = Promise.resolve();

const assetError = (error: unknown): Error => {
  const message = error instanceof Error ? error.message : "BusyTeX compile failed";
  if (/fetch|404|worker|initialize|BusyTeX/i.test(message)) {
    return new Error(
      `${message}. TeX Live basic is loaded once from /busytex. Run npm run download:busytex in apps/web if that directory is empty.`,
    );
  }
  return error instanceof Error ? error : new Error(message);
};

const runner = (): Promise<BusyTexRunner> => {
  if (!runnerPromise) {
    const created = new BusyTexRunner({
      busytexBasePath: BUSYTEX_BASE_PATH,
      engineMode: "combined",
      preloadDataPackages: [PRELOAD_DATA_PACKAGE],
    });
    runnerPromise = created.initialize(true).then(
      () => created,
      (error: unknown) => {
        runnerPromise = null;
        created.terminate();
        throw assetError(error);
      },
    );
  }
  return runnerPromise;
};

/**
 * Compile one TeX buffer with pdfLaTeX. The worker and the basic TeX Live
 * set stay up for the page; missing packages are fetched from TeX Live 2026.
 */
export const compileTex = (
  source: string,
  additionalFiles: TexInputFile[] = [],
): Promise<CompileResult> => {
  const job = queue.then(async () => {
    const pdflatex = new PdfLatex(await runner());
    const result = await pdflatex.compile(compileRequest(source, additionalFiles));
    const pdf = result.pdf;
    return {
      pdf: pdf && pdf.byteLength > 0 ? pdf : null,
      log: result.log ?? "",
    };
  });
  queue = job.then(
    () => undefined,
    () => undefined,
  );
  return job;
};
