import type { JSX } from "react";
import { MarkdownContent } from "@/components/ui/markdown";
import type { FilePreviewContentProps } from "@/lib/file-preview-plugins";

/**
 * A markdown file's preview (L07-2): the app's document style — headings,
 * lists, code, math — the same renderer knowledge documents use. It used
 * `prose`, which no typography plugin backs, so it rendered as plain text.
 */
export const MarkdownPreview = ({ content }: FilePreviewContentProps): JSX.Element => (
  <article className="max-w-[48rem] px-6 py-4">
    <MarkdownContent text={content} />
  </article>
);
