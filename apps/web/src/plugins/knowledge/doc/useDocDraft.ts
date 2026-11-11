/**
 * A knowledge page's unsaved body (L10): edits collect in a draft (● on the
 * tab, ⌘S saves, leaving asks); an edit marked `save` (a task box) writes at
 * once. A failed save keeps the draft and reports why.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { knowledgeApi } from "@/api";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
import { knowledgeKeys } from "../queries";

export interface DocDraft {
  body: string;
  dirty: boolean;
  saving: boolean;
  error: string | null;
  update: (edit: (body: string) => string, options?: { save?: boolean }) => void;
  save: () => void;
  clearError: () => void;
}

export const useDocDraft = (note: NoteDetailResponse): DocDraft => {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedRef = useRef(note.body);
  savedRef.current = note.body;
  const pendingSave = useRef<string | null>(null);

  // A different document starts clean.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset on identity only
  useEffect(() => {
    setDraft(null);
    setError(null);
  }, [note.relPath]);

  const persist = useCallback(
    async (body: string): Promise<void> => {
      setSaving(true);
      setError(null);
      try {
        const updated = await knowledgeApi.editDoc(note.relPath, body);
        queryClient.setQueryData<NoteDetailResponse>(knowledgeKeys.note(note.relPath), updated);
        void queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
        setDraft((current) => (current === body ? null : current));
      } catch (err) {
        setError(
          `Couldn't save ${note.name} — ${err instanceof Error ? err.message : "the server refused it"}. Your edits are kept.`,
        );
      } finally {
        setSaving(false);
      }
    },
    [note.relPath, note.name, queryClient],
  );

  const update = useCallback(
    (edit: (body: string) => string, options?: { save?: boolean }): void => {
      setDraft((current) => {
        const next = edit(current ?? savedRef.current);
        if (options?.save) pendingSave.current = next;
        return next === savedRef.current ? null : next;
      });
    },
    [],
  );

  // A `save` edit is written after the draft has taken it.
  useEffect(() => {
    const body = pendingSave.current;
    if (body === null) return;
    pendingSave.current = null;
    void persist(body);
  });

  const body = draft ?? note.body;
  const dirty = draft !== null && draft !== note.body;
  const save = useCallback(() => {
    if (dirty && !saving) void persist(body);
  }, [dirty, saving, persist, body]);

  return { body, dirty, saving, error, update, save, clearError: () => setError(null) };
};
