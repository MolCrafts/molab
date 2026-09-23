import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
import "@milkdown/crepe/theme/frame.css";
import { type JSX, useEffect, useRef, useState } from "react";
import { knowledgeApi } from "@/api";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
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
}: {
  note: NoteDetailResponse;
  onSaved: (updated: NoteDetailResponse) => void;
}): JSX.Element => {
  const hostRef = useRef<HTMLDivElement>(null);
  const crepeRef = useRef<Crepe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef(note.body);
  bodyRef.current = note.body;

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
    const host = hostRef.current;
    host?.addEventListener("focusout", onBlur);
    return () => host?.removeEventListener("focusout", onBlur);
  }, [note.relPath, onSaved]);

  return (
    <div className="min-h-[24rem]">
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
