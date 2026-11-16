/**
 * WYSIWYG editing of one prose block in place (L10): Milkdown Crepe on the
 * block's markdown. Every change flows to the page draft (● and ⌘S save the
 * file); Esc or a click outside ends the edit. "/" offers the `<molab-…>`
 * components and the MkDocs blocks; picking one ends the edit and puts the
 * block where the "/" was.
 */

import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
import "@milkdown/crepe/theme/frame.css";
import { commandsCtx, editorViewCtx } from "@milkdown/kit/core";
import { clearTextInCurrentBlockCommand } from "@milkdown/kit/preset/commonmark";
import type { LucideIcon } from "lucide-react";
import { createElement, type JSX, useEffect, useRef, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { knowledgeApi } from "@/api";
import { restoreKnowledgeMedia, rewriteKnowledgeMedia } from "../knowledgeMedia";
import { SLASH_BLOCKS } from "./slashBlocks";

/** Placeholder line the "/" insert leaves where the new block goes. */
export const INSERT_TOKEN = "MOLABINSERTPOINT";

const svg = (icon: LucideIcon): string =>
  renderToStaticMarkup(
    createElement(icon, {
      size: 20,
      strokeWidth: 1.6,
      "aria-hidden": true,
      className: "doc-slash-icon",
    }),
  );

export interface InlineEditorProps {
  relPath: string;
  markdown: string;
  /** Every edit, as markdown with workspace paths restored. */
  onChange: (markdown: string) => void;
  /** End of editing (Esc, click outside). */
  onDone: () => void;
  /** "/" picked a block: *markdown* holds INSERT_TOKEN on its own line where it goes. */
  onInsert: (markdown: string, block: string) => void;
}

export const InlineEditor = ({
  relPath,
  markdown,
  onChange,
  onDone,
  onInsert,
}: InlineEditorProps): JSX.Element => {
  const hostRef = useRef<HTMLDivElement>(null);
  const crepeRef = useRef<Crepe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const callbacks = useRef({ onChange, onDone, onInsert });
  callbacks.current = { onChange, onDone, onInsert };

  // Mount once per edit session; the initial markdown is the block as it was.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see above
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const restore = (md: string): string => restoreKnowledgeMedia(md, relPath);
    const crepe = new Crepe({
      root: host,
      defaultValue: rewriteKnowledgeMedia(markdown, relPath),
      features: {
        [Crepe.Feature.Latex]: true,
        [Crepe.Feature.AI]: false,
        [Crepe.Feature.ImageBlock]: false,
      },
      featureConfigs: {
        [Crepe.Feature.BlockEdit]: {
          buildMenu: (builder) => {
            const group = builder.addGroup("molab", "Components");
            for (const item of SLASH_BLOCKS) {
              group.addItem(item.key, {
                label: item.label,
                icon: svg(item.icon),
                onRun: (ctx) => {
                  ctx.get(commandsCtx).call(clearTextInCurrentBlockCommand.key);
                  const view = ctx.get(editorViewCtx);
                  view.dispatch(view.state.tr.insertText(INSERT_TOKEN));
                  callbacks.current.onInsert(restore(crepe.getMarkdown()), item.markdown());
                },
              });
            }
          },
        },
      },
    });
    crepe.on((listener) => {
      listener.markdownUpdated((_ctx, next) => callbacks.current.onChange(restore(next)));
    });
    crepeRef.current = crepe;
    let cancelled = false;
    void crepe.create().then(() => {
      if (cancelled) void crepe.destroy();
      else crepe.editor.action((ctx) => ctx.get(editorViewCtx).focus());
    });
    return () => {
      cancelled = true;
      void crepe.destroy();
      crepeRef.current = null;
    };
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        callbacks.current.onDone();
      }
    };
    const onPaste = (event: ClipboardEvent): void => {
      const file = [...(event.clipboardData?.files ?? [])].find((item) =>
        item.type.startsWith("image/"),
      );
      if (!file) return;
      event.preventDefault();
      void knowledgeApi
        .uploadDocMedia(relPath, file)
        .then((relative) =>
          crepeRef.current?.editor.action((ctx) => {
            const view = ctx.get(editorViewCtx);
            view.dispatch(view.state.tr.insertText(`![](${relative})`));
          }),
        )
        .catch((err: unknown) => setError(err instanceof Error ? err.message : "Upload failed."));
    };
    const onPointerDown = (event: PointerEvent): void => {
      const target = event.target;
      if (!(target instanceof Node) || host.contains(target)) return;
      // Crepe's menus and toolbars are portalled; a click in them is still editing.
      if (target instanceof Element && target.closest(".milkdown, [data-show]")) return;
      callbacks.current.onDone();
    };
    host.addEventListener("keydown", onKeyDown);
    host.addEventListener("paste", onPaste);
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => {
      host.removeEventListener("keydown", onKeyDown);
      host.removeEventListener("paste", onPaste);
      document.removeEventListener("pointerdown", onPointerDown, true);
    };
  }, [relPath]);

  return (
    <div className="doc-inline-editor -ml-10 rounded-control bg-surface ring-1 ring-accent">
      {error ? (
        <p role="alert" className="py-1 text-label text-status-failed">
          {error}
        </p>
      ) : null}
      <div ref={hostRef} className="crepe" />
    </div>
  );
};
