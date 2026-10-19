import { MarkdownContent as MarkdownBody } from "@molcrafts/ui-markdown";
import type { JSX, ReactNode } from "react";
import { useContext } from "react";
import { isMolabRef, resolveMolabRef } from "@/lib/molab-ref";
import { MolabRefIndexContext } from "@/lib/molab-ref-context";

/** A `molab:` link becomes an in-app chip, or muted text when it cannot resolve. */
const MolabRefLink = ({ href, children }: { href: string; children: ReactNode }): JSX.Element => {
  const index = useContext(MolabRefIndexContext);
  const resolved = index ? resolveMolabRef(href, index) : null;
  if (!resolved) {
    return (
      <span
        data-molab-ref="unresolved"
        title={href}
        className="text-muted-foreground underline decoration-dotted underline-offset-2"
      >
        {children}
      </span>
    );
  }
  return (
    <a
      href={resolved.path}
      data-molab-ref={resolved.kind}
      title={href}
      className="rounded-control border border-border bg-muted px-1 no-underline"
    >
      {children}
    </a>
  );
};

export const MarkdownContent = ({
  text,
  className,
}: {
  text: string;
  className?: string;
}): JSX.Element => (
  <MarkdownBody
    text={text}
    className={className}
    urlTransform={(url) => (isMolabRef(url) ? url : undefined)}
    components={{
      a: ({ children, href }) =>
        isMolabRef(href) ? (
          <MolabRefLink href={href ?? ""}>{children}</MolabRefLink>
        ) : href?.startsWith("/") ? (
          <a href={href}>{children}</a>
        ) : (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
    }}
  />
);
