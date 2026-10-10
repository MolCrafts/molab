import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
import "@milkdown/crepe/theme/frame.css";
import { editorViewCtx } from "@milkdown/kit/core";
import { ImagePlus } from "lucide-react";
import { type JSX, useEffect, useRef, useState } from "react";
import { knowledgeApi } from "@/api";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
import { WorkbenchAction } from "@/components/workbench";
import {
  proxyKnowledgeImageUrl,
  restoreKnowledgeMedia,
  rewriteKnowledgeMedia,
} from "@/plugins/knowledge/knowledgeMedia";
import { buildNoteDocUpdate, isDirty } from "@/plugins/knowledge/noteDraft";

/**
 * Milkdown Crepe — Notion-like WYSIWYG whose save payload is markdown.
 * Frontmatter stays on disk; this surface edits the body only and the PUT
 * sends the full document (existing YAML + new body).
 */
export const NoteEditor = ({
  note,
  onSaved,
  onOpenHref,
}: {
  note: NoteDetailResponse;
  onSaved: (updated: NoteDetailResponse) => void;
  onOpenHref?: (href: string) => void;
}): JSX.Element => {
  const hostRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const crepeRef = useRef<Crepe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef(note.body);
  bodyRef.current = note.body;
  const openHrefRef = useRef(onOpenHref);
  openHrefRef.current = onOpenHref;

  const insertFigure = async (file: File): Promise<void> => {
    const crepe = crepeRef.current;
    if (!crepe) return;
    setError(null);
    try {
      const relative = await knowledgeApi.uploadDocMedia(note.relPath, file);
      crepe.editor.action((ctx) => {
        const view = ctx.get(editorViewCtx);
        view.dispatch(view.state.tr.insertText(`\n\n![](${relative})\n`));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to insert image.");
    }
  };
  const insertRef = useRef(insertFigure);
  insertRef.current = insertFigure;

  // Remount only when the document identity changes. Body is the initial
  // value; live edits live in Crepe, saves go through persist.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see above
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const crepe = new Crepe({
      root: host,
      defaultValue: rewriteKnowledgeMedia(note.body, note.relPath),
      features: {
        [Crepe.Feature.Latex]: true,
        [Crepe.Feature.AI]: false,
        // ImageBlock serializes alt as the aspect ratio ("1.00") and would
        // clobber figure captions on every blur-save.
        [Crepe.Feature.ImageBlock]: false,
      },
      featureConfigs: {
        [Crepe.Feature.ImageBlock]: {
          proxyDomURL: (url) => proxyKnowledgeImageUrl(note.relPath, url),
        },
      },
    });
    crepeRef.current = crepe;
    let cancelled = false;
    void crepe.create().then(() => {
      if (cancelled) void crepe.destroy();
    });
    return () => {
      cancelled = true;
      void crepe.destroy();
      crepeRef.current = null;
    };
  }, [note.relPath]);

  useEffect(() => {
    const persist = async (): Promise<void> => {
      const crepe = crepeRef.current;
      if (!crepe) return;
      const body = restoreKnowledgeMedia(crepe.getMarkdown(), note.relPath);
      if (!isDirty(bodyRef.current, body)) return;
      setError(null);
      try {
        const update = buildNoteDocUpdate(note.relPath, body);
        const persisted = await knowledgeApi.editDoc(update.path, update.body);
        onSaved(persisted);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save.");
      }
    };
    const onBlur = (): void => {
      void persist();
    };
    const onPaste = (event: Event): void => {
      const clipboard = (event as ClipboardEvent).clipboardData;
      const file = clipboard
        ? [...clipboard.files].find((item) => item.type.startsWith("image/"))
        : undefined;
      if (!file) return;
      event.preventDefault();
      void insertRef.current(file);
    };
    const onClick = (event: Event): void => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest("a");
      const href = anchor?.getAttribute("href") ?? "";
      if (!href.startsWith("molab:") || !openHrefRef.current) return;
      event.preventDefault();
      openHrefRef.current(href.split("#")[0] ?? href);
    };
    const host = hostRef.current;
    host?.addEventListener("focusout", onBlur);
    host?.addEventListener("paste", onPaste);
    host?.addEventListener("click", onClick);
    return () => {
      host?.removeEventListener("focusout", onBlur);
      host?.removeEventListener("paste", onPaste);
      host?.removeEventListener("click", onClick);
    };
  }, [note.relPath, onSaved]);

  return (
    <div className="min-h-[24rem]">
      <div className="mb-2 flex items-center gap-2">
        <WorkbenchAction
          kind="ghost"
          size="compact"
          type="button"
          onClick={() => fileRef.current?.click()}
        >
          <ImagePlus className="size-icon-sm" />
          Insert image
        </WorkbenchAction>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void insertFigure(file);
          }}
        />
      </div>
      {error ? (
        <p role="alert" className="mb-2 text-label text-destructive">
          {error}
        </p>
      ) : null}
      <div
        ref={hostRef}
        className="crepe min-h-[24rem] [&_img]:my-2 [&_img]:max-w-full [&_img]:rounded-control [&_img]:border [&_img]:border-border/60"
      />
    </div>
  );
};
