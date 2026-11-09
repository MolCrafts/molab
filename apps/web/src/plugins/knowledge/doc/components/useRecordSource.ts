/**
 * The class record a planning component edits: the current document's (via
 * `useDoc().saveRecord`) or, with a `src` attribute, another document's (read
 * through its note query, written with PATCH /api/knowledge/doc/record).
 *
 * A write is optimistic: the new record shows at once and stays until the
 * source record changes (the refetch); a failure reverts it and leaves a
 * readable error. Every write sends the whole record.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiErrorMessage } from "@/api/errors";
import { KnowledgeService } from "@/api/generated/services/KnowledgeService";
import type { KnowledgeClass } from "../../knowledgeClass";
import { knowledgeKeys, knowledgeNoteQueryOptions } from "../../queries";
import { useDoc } from "../context";

export type RecordSource =
  | { state: "loading" }
  | { state: "missing"; message: string }
  | {
      state: "ready";
      record: Readonly<Record<string, unknown>>;
      /** The class when the record is the current document's; null for a `src` document. */
      cls: KnowledgeClass | null;
      writable: boolean;
      error: string | null;
      commit: (next: Record<string, unknown>) => void;
    };

const EMPTY: Readonly<Record<string, unknown>> = {};

interface Draft {
  base: unknown;
  next: Record<string, unknown>;
}

export const useRecordSource = (src: string | undefined): RecordSource => {
  const doc = useDoc();
  const queryClient = useQueryClient();
  const path = src?.trim() ?? "";
  const remote = useQuery({ ...knowledgeNoteQueryOptions(path), enabled: path.length > 0 });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (path && remote.isPending) return { state: "loading" };
  if (path && remote.isError) {
    return { state: "missing", message: apiErrorMessage(remote.error, `Cannot read ${path}.`) };
  }
  const base = path ? (remote.data?.record ?? EMPTY) : doc.record;
  const record = draft && draft.base === base ? draft.next : base;

  const save = async (next: Record<string, unknown>): Promise<void> => {
    if (!path) return doc.saveRecord(next);
    await KnowledgeService.replaceDocRecord(path, { record: next });
    await queryClient.invalidateQueries({ queryKey: knowledgeKeys.note(path) });
  };

  const commit = (next: Record<string, unknown>): void => {
    setError(null);
    setDraft({ base, next });
    save(next).catch((reason: unknown) => {
      setDraft(null);
      setError(apiErrorMessage(reason, "The change was not saved."));
    });
  };

  return {
    state: "ready",
    record,
    cls: path ? null : doc.cls,
    writable: doc.writable,
    error,
    commit,
  };
};
