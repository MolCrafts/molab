import { useCallback, useEffect, useRef, useState } from "react";
import { WorkbenchOperationState } from "@/components/workbench";
import type { FilePreviewContentProps } from "@/lib/file-preview-plugins";
import { type CompileResult, compileTex } from "./engine";
import { loadManuscriptFiles } from "./load-manuscript";
import { logSummary } from "./log";

const COMPILE_DEBOUNCE_MS = 500;

const pdfUrlFrom = (pdf: Uint8Array): string => {
  const copy = new Uint8Array(pdf);
  return URL.createObjectURL(new Blob([copy], { type: "application/pdf" }));
};

/**
 * Preview host for one `.tex` file. pdfLaTeX runs in a worker and the PDF
 * is shown here. The editor keeps feeding source as the user types, so the
 * compile is debounced and a superseded result is dropped.
 */
export const TexPreview = ({ content, name, path }: FilePreviewContentProps): JSX.Element => {
  const [phase, setPhase] = useState<"idle" | "running" | "ready" | "error">("idle");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [log, setLog] = useState("");
  const [detail, setDetail] = useState("");
  const pdfUrlRef = useRef<string | null>(null);

  const replacePdfUrl = useCallback((next: string | null): void => {
    if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
    pdfUrlRef.current = next;
    setPdfUrl(next);
  }, []);

  useEffect(() => {
    if (content.trim().length === 0) {
      setPhase("idle");
      setLog("");
      setDetail("");
      replacePdfUrl(null);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setPhase("running");
      void loadManuscriptFiles(content, path)
        .then((files) => compileTex(content, files))
        .then(
          (result: CompileResult) => {
            if (cancelled) return;
            setLog(result.log);
            if (result.pdf) {
              replacePdfUrl(pdfUrlFrom(result.pdf));
              setPhase("ready");
              setDetail("");
              return;
            }
            replacePdfUrl(null);
            setPhase("error");
            setDetail(logSummary(result.log));
          },
          (error: unknown) => {
            if (cancelled) return;
            const message = error instanceof Error ? error.message : "BusyTeX compile failed";
            replacePdfUrl(null);
            setPhase("error");
            setDetail(message);
            setLog(message);
          },
        );
    }, COMPILE_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [content, path, replacePdfUrl]);

  useEffect(() => {
    return () => {
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
      pdfUrlRef.current = null;
    };
  }, []);

  if (content.trim().length === 0) {
    return (
      <WorkbenchOperationState
        kind="empty"
        title="Nothing to compile"
        detail="This TeX file is empty."
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      {phase === "running" ? (
        <WorkbenchOperationState
          kind="running"
          title="Compiling TeX…"
          detail="The engine stays loaded. The first compile fetches any package that is not in the basic set."
          className="min-h-0 flex-1"
        />
      ) : null}
      {phase === "error" ? (
        <WorkbenchOperationState kind="error" title="Could not compile TeX" detail={detail} />
      ) : null}
      {phase === "error" ? (
        <pre className="min-h-0 flex-1 overflow-auto border-t border-border px-3 py-3 font-mono text-label text-foreground">
          {content}
        </pre>
      ) : null}
      {phase === "ready" && pdfUrl ? (
        <iframe
          title={`TeX preview of ${name}`}
          src={pdfUrl}
          className="min-h-0 w-full flex-1 border-0"
        />
      ) : null}
      {log && phase !== "running" ? (
        <details className="flex-none border-t border-border">
          <summary className="cursor-pointer px-3 py-2 text-label text-muted-foreground">
            Engine log
          </summary>
          <pre className="max-h-48 overflow-auto px-3 pb-3 font-mono text-label text-muted-foreground">
            {log}
          </pre>
        </details>
      ) : null}
    </div>
  );
};
