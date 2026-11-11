/**
 * What an asset is, for people (L08): a structure, a table, model weights, an
 * image, text, or plain data. Decided from the name and the recorded media
 * type; the kind picks the icon, the tint and the preview.
 */

import { Atom, Cpu, Database, FileText, Image, type LucideIcon, Table } from "lucide-react";
import { isStructurePreviewName } from "@/lib/structure-files";

export type AssetKind = "structure" | "table" | "model" | "image" | "text" | "data";

export interface AssetKindMeta {
  label: string;
  icon: LucideIcon;
  /** Icon ink (`text-asset-*`). */
  ink: string;
  /** Tile ground: the ink washed into the surface. */
  ground: string;
}

/** Class names are spelled whole so Tailwind sees them. */
export const ASSET_KIND_META: Record<AssetKind, AssetKindMeta> = {
  structure: {
    label: "Structure",
    icon: Atom,
    ink: "text-asset-structure",
    ground: "bg-asset-structure/12",
  },
  table: { label: "Table", icon: Table, ink: "text-asset-table", ground: "bg-asset-table/12" },
  model: {
    label: "Model weights",
    icon: Cpu,
    ink: "text-asset-model",
    ground: "bg-asset-model/12",
  },
  image: { label: "Image", icon: Image, ink: "text-asset-image", ground: "bg-asset-image/12" },
  text: { label: "Text", icon: FileText, ink: "text-asset-text", ground: "bg-asset-text/12" },
  data: { label: "Data", icon: Database, ink: "text-asset-text", ground: "bg-asset-text/12" },
};

const TABLE = /\.(csv|tsv)$/i;
const IMAGE = /\.(png|jpe?g|gif|webp|svg|bmp)$/i;
const MODEL = /\.(pt|pth|ckpt|onnx|safetensors|h5|keras|pb|joblib|pkl|pickle|npz)$/i;
const TEXT = /\.(txt|log|out|err|md|markdown|json|jsonl|ya?ml|toml|ini|cfg|py|sh|tex|in)$/i;

/** The kind of an asset, from its name first and its media type second. */
export const assetKindOf = (name: string, mediaType?: string | null): AssetKind => {
  const media = (mediaType ?? "").toLowerCase();
  if (isStructurePreviewName(name) || media.startsWith("chemical/")) return "structure";
  if (TABLE.test(name) || media === "text/csv" || media === "text/tab-separated-values")
    return "table";
  if (IMAGE.test(name) || media.startsWith("image/")) return "image";
  if (MODEL.test(name)) return "model";
  if (TEXT.test(name) || media.startsWith("text/") || media === "application/json") return "text";
  return "data";
};

/** The name that carries the extension: the payload file's, else the title. */
export const assetFileName = (asset: { name: string; file?: string }): string =>
  asset.file?.split("/").filter(Boolean).at(-1) || asset.name;

/** An asset summary's kind (file name first, then media type). */
export const kindOfAsset = (asset: {
  name: string;
  file?: string;
  mediaType?: string | null;
}): AssetKind => assetKindOf(assetFileName(asset), asset.mediaType);
