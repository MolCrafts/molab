/**
 * `<molab-figure src=… caption=…>` (L10): an image with a caption bar. `src` is
 * a path relative to the document (served through the workspace file blob
 * route) or a `molab:` asset ref (served through the asset's download route).
 */

import { Image as ImageIcon } from "lucide-react";
import { type JSX, useState } from "react";
import { assetsApi } from "@/api/assets";
import type { RendererSnapshot } from "@/app/types";
import { isMolabRef, type MolabRefTarget } from "@/lib/molab-ref";
import { proxyKnowledgeImageUrl } from "../../knowledgeMedia";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { useDoc } from "../context";
import { ComponentFrame, ComponentNotice } from "../frame";
import { resolveDocRef } from "../RefChip";

const NAME = "molab-figure";

type Source = { url: string } | { problem: string };

const assetSource = (
  ref: string,
  refIndex: ReadonlyMap<string, MolabRefTarget>,
  snapshot: RendererSnapshot,
): Source => {
  const assets = snapshot.assets ?? [];
  const target = resolveDocRef(ref, refIndex, snapshot)?.target;
  const asset =
    assets.find((item) => item.ref === ref) ??
    (target?.kind === "asset" ? assets.find((item) => item.id === target.assetId) : undefined);
  if (!asset) return { problem: `${ref} does not resolve.` };
  // The server serves an asset's bytes through its project; a workspace-level
  // asset has no download route yet.
  if (!asset.projectId)
    return { problem: `${asset.name} has no download route (not in a project).` };
  return { url: assetsApi.downloadUrl(asset.projectId, asset.id) };
};

const Picture = ({
  url,
  caption,
  alt,
}: {
  url: string;
  caption: string | undefined;
  alt: string;
}): JSX.Element => {
  // Whether the browser could draw the bytes is UI state, not server data.
  const [broken, setBroken] = useState(false);
  if (broken) return <ComponentNotice name={NAME}>Cannot show {alt}.</ComponentNotice>;
  return (
    <ComponentFrame label={caption || alt}>
      <img
        src={url}
        alt={alt}
        onError={() => setBroken(true)}
        className="mx-auto block h-auto max-w-full"
      />
      {caption ? (
        <div className="flex items-center gap-2 border-t border-border px-3 py-row-pad text-label text-muted-foreground">
          <ImageIcon aria-hidden className="size-icon-sm flex-none" />
          <span className="min-w-0 truncate">{caption}</span>
        </div>
      ) : null}
    </ComponentFrame>
  );
};

export const Figure = ({ attrs }: DocComponentProps): JSX.Element => {
  const doc = useDoc();
  const src = attrs.src?.trim();
  if (!src) return <ComponentNotice name={NAME}>Needs a src= attribute.</ComponentNotice>;
  const source: Source = isMolabRef(src)
    ? assetSource(src, doc.refIndex, doc.snapshot)
    : { url: proxyKnowledgeImageUrl(doc.relPath, src) };
  if ("problem" in source) return <ComponentNotice name={NAME}>{source.problem}</ComponentNotice>;
  // Keyed by the URL so a new src starts unbroken.
  return (
    <Picture
      key={source.url}
      url={source.url}
      caption={attrs.caption}
      alt={attrs.alt || attrs.caption || src}
    />
  );
};

export const figureSpec: DocComponentSpec = {
  name: NAME,
  label: "Figure",
  description: "An image beside the document, or an asset, with its caption",
  keywords: ["figure", "image", "picture", "plot", "asset", "caption"],
  icon: ImageIcon,
  template: { src: "", caption: "" },
  Component: Figure,
};
