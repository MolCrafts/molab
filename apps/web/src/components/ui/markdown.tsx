import { type JSX, Suspense } from "react";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";

const MarkdownContentImpl = lazyWithPrefetch(() =>
  import("./markdown-impl").then((module) => ({ default: module.MarkdownContent })),
);

export const prefetchMarkdown = (): void => {
  void MarkdownContentImpl.prefetch();
};

/**
 * Token-styled markdown. The KaTeX/remark stack is loaded on first use so the
 * shell is not blocked by math rendering. Until that chunk lands, the source
 * text is shown immediately.
 */
export const MarkdownContent = ({
  text,
  className,
}: {
  text: string;
  className?: string;
}): JSX.Element => (
  <Suspense
    fallback={
      <p className="whitespace-pre-wrap text-body-lg leading-relaxed text-foreground [overflow-wrap:anywhere]">
        {text}
      </p>
    }
  >
    <MarkdownContentImpl text={text} className={className} />
  </Suspense>
);
