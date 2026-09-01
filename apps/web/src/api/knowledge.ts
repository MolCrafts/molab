import { EmbedRequest } from "@/api/generated/models/EmbedRequest";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import { KnowledgeService } from "@/api/generated/services/KnowledgeService";

export type { EntityCard } from "@/api/generated/models/EntityCard";

export type EmbedTargetKind = "run" | "experiment" | "asset" | "reference";
export type EmbedRole = "derived_from" | "cites" | "supersedes" | "records" | "references";

const EMBED_TARGET_KIND: Record<EmbedTargetKind, EmbedRequest.target_kind> = {
  run: EmbedRequest.target_kind.RUN,
  experiment: EmbedRequest.target_kind.EXPERIMENT,
  asset: EmbedRequest.target_kind.ASSET,
  reference: EmbedRequest.target_kind.REFERENCE,
};

export const knowledgeApi = {
  listKnowledge: (options: { tag?: string | null; status?: string | null } = {}) =>
    KnowledgeService.listKnowledge(options.tag ?? undefined, options.status ?? undefined),
  getNote: (path: string) => KnowledgeService.getNote(path),
  searchKnowledge: (q: string, options: { type?: string | null; tag?: string | null } = {}) =>
    KnowledgeService.searchKnowledge(q, options.type ?? undefined, options.tag ?? undefined),
  getNoteCards: async (path: string): Promise<EntityCard[]> => {
    const detail = await KnowledgeService.getNote(path);
    return detail.cards ?? [];
  },
  embedEntity: (
    path: string,
    request: {
      targetKind: EmbedTargetKind;
      target: string;
      role?: EmbedRole | null;
      text?: string | null;
    },
  ) =>
    KnowledgeService.embedDoc(path, {
      target_kind: EMBED_TARGET_KIND[request.targetKind],
      target: request.target,
      role: request.role ?? null,
      text: request.text ?? null,
    }),
  editDoc: (path: string, body: string) => KnowledgeService.editDoc(path, { body }),
  updateDocMeta: (path: string, patch: { tags?: string[]; status?: string }) =>
    KnowledgeService.updateDocMeta(path, patch),
  createDoc: (name: string, options: { parentPath?: string | null; body?: string } = {}) =>
    KnowledgeService.createDoc({
      name,
      parentPath: options.parentPath ?? null,
      body: options.body ?? "",
    }),
  renameDoc: (path: string, name: string) => KnowledgeService.moveDoc(path, { name }),
  moveDoc: (path: string, parentPath: string) => KnowledgeService.moveDoc(path, { parentPath }),
  deleteDoc: async (path: string): Promise<void> => {
    await KnowledgeService.deleteDoc(path);
  },
  getBacklinks: (path: string) => KnowledgeService.getBacklinks(path),
  docExportUrl: (path: string): string =>
    `/api/knowledge/doc/export?path=${encodeURIComponent(path)}`,
};
