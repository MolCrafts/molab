/**
 * `<molab-citation>` (L10, Figma v4_01): a reference — its title, a muted
 * "authors · year · venue" line, then link chips: the DOI (mono, to
 * doi.org), the PDF, the Zotero item.
 */

import { BookOpen, FileText, Link as LinkIcon, Quote } from "lucide-react";
import type { JSX, ReactNode } from "react";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentFrame, ComponentNotice } from "../frame";

const NAME = "molab-citation";

const chipClass =
  "inline-flex h-6 items-center gap-1 rounded-control border border-border bg-surface px-2 text-label text-foreground no-underline hover:border-input";

/** `10.1080/…`, `doi:10.1080/…` or a doi.org URL → the bare DOI. */
export const bareDoi = (doi: string): string =>
  doi
    .trim()
    .replace(/^doi:\s*/i, "")
    .replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");

const Chip = ({ href, children }: { href: string; children: ReactNode }): JSX.Element => (
  <a href={href} target="_blank" rel="noreferrer noopener" className={chipClass}>
    {children}
  </a>
);

export const Citation = ({ attrs }: DocComponentProps): JSX.Element => {
  const title = attrs.title?.trim();
  if (!title)
    return (
      <ComponentNotice name={NAME}>Set title (and authors, year, venue, doi).</ComponentNotice>
    );
  const byline = [attrs.authors, attrs.year, attrs.venue]
    .map((part) => part?.trim())
    .filter(Boolean)
    .join(" · ");
  const doi = attrs.doi ? bareDoi(attrs.doi) : "";
  const link = attrs.url?.trim();
  return (
    <ComponentFrame label="Citation">
      <div className="space-y-1 px-3 py-3">
        <p className="text-body font-medium text-foreground">
          {link ? (
            <a href={link} target="_blank" rel="noreferrer noopener" className="hover:underline">
              {title}
            </a>
          ) : (
            title
          )}
        </p>
        {byline ? <p className="text-label text-muted-foreground">{byline}</p> : null}
        {doi || attrs.pdf || attrs.zotero ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {doi ? (
              <Chip href={`https://doi.org/${doi}`}>
                <LinkIcon aria-hidden className="size-icon-sm text-muted-foreground" />
                <span className="font-mono">{doi}</span>
              </Chip>
            ) : null}
            {attrs.pdf ? (
              <Chip href={attrs.pdf}>
                <FileText aria-hidden className="size-icon-sm text-muted-foreground" />
                PDF
              </Chip>
            ) : null}
            {attrs.zotero ? (
              <Chip href={attrs.zotero}>
                <BookOpen aria-hidden className="size-icon-sm text-muted-foreground" />
                Zotero
              </Chip>
            ) : null}
          </div>
        ) : null}
      </div>
    </ComponentFrame>
  );
};

export const citationSpec: DocComponentSpec = {
  name: NAME,
  label: "Citation",
  description: "A reference: title, authors · year · venue, DOI / PDF / Zotero.",
  keywords: ["citation", "reference", "paper", "doi", "literature", "zotero"],
  icon: Quote,
  template: { title: "", authors: "", year: "", doi: "" },
  Component: Citation,
};
