/**
 * A knowledge page's editor actions (L10), in the tab row: Save (only while
 * edited; ⌘S first), Export, and ⋯ — Rename…, Move to…, the status words,
 * Copy path, Delete…. Icons only; the menu is words only.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Download, MoreHorizontal, Save } from "lucide-react";
import { type JSX, useState } from "react";
import { knowledgeApi } from "@/api";
import type { RendererSnapshot } from "@/app/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { usePrompt } from "@/components/PromptDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";
import { HostPickerDialog } from "../HostPickerDialog";
import { listHostOptions } from "../knowledgeDocTree";
import { knowledgeKeys } from "../queries";
import { useKnowledgeDocs } from "../useKnowledgeDocs";

const STATUS_WORDS = ["draft", "active", "archived"] as const;

export interface DocActionsProps {
  relPath: string;
  name: string;
  hostPath: string;
  status: string | null;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  /** After a rename / move / delete: where the page should go ("" = the landing). */
  onRelocated: (path: string) => void;
  snapshot: RendererSnapshot;
  writable: boolean;
}

export const DocActions = ({
  relPath,
  name,
  hostPath,
  status,
  dirty,
  saving,
  onSave,
  onRelocated,
  snapshot,
  writable,
}: DocActionsProps): JSX.Element => {
  const queryClient = useQueryClient();
  const { renameDoc, moveDoc, deleteDoc } = useKnowledgeDocs();
  const { prompt, dialog: promptDialog } = usePrompt();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [moving, setMoving] = useState(false);

  const setStatus = useMutation({
    mutationFn: (next: string) => knowledgeApi.updateDocMeta(relPath, { status: next }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: knowledgeKeys.lists() }),
    onError: (err) => toast(err instanceof Error ? err.message : "Couldn't set the status."),
  });

  const guard = async (run: () => Promise<void>, done: string): Promise<void> => {
    try {
      await run();
      toast(done);
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err));
    }
  };

  const rename = async (): Promise<void> => {
    const next = await prompt({
      title: "Rename document",
      label: "New name",
      defaultValue: name,
      confirmLabel: "Rename",
    });
    if (!next || next === name) return;
    await guard(async () => {
      await renameDoc(relPath, next);
      onRelocated("");
    }, "Document renamed.");
  };

  const remove = async (): Promise<void> => {
    const ok = await confirm({
      title: `Delete document “${name}”?`,
      description:
        "The file is removed from the workspace. Documents that cite it keep a broken link.",
      confirmLabel: "Delete document",
      destructive: true,
    });
    if (!ok) return;
    await guard(async () => {
      await deleteDoc(relPath);
      onRelocated("");
    }, "Document deleted.");
  };

  return (
    <div className="flex items-center gap-hairline">
      {dirty ? (
        <WorkbenchIconAction
          label={saving ? "Saving…" : "Save"}
          shortcut="⌘S"
          disabled={saving}
          className="text-accent"
          onClick={onSave}
        >
          <Save aria-hidden />
        </WorkbenchIconAction>
      ) : null}
      <WorkbenchIconAction label="Export" asChild>
        <a href={knowledgeApi.docExportUrl(relPath)} download>
          <Download aria-hidden />
        </a>
      </WorkbenchIconAction>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More actions">
            <MoreHorizontal aria-hidden />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuItem disabled={!writable} onSelect={() => void rename()}>
            Rename…
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!writable} onSelect={() => setMoving(true)}>
            Move to…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {STATUS_WORDS.map((word) => (
            <DropdownMenuItem
              key={word}
              disabled={!writable}
              onSelect={() => setStatus.mutate(word)}
              className="justify-between"
            >
              {word.charAt(0).toUpperCase() + word.slice(1)}
              {status === word ? <Check aria-hidden className="size-icon-sm" /> : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => {
              void navigator.clipboard.writeText(relPath);
              toast("Copied path");
            }}
          >
            Copy path
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!writable}
            onSelect={() => void remove()}
            className="text-status-failed"
          >
            Delete…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {promptDialog}
      {confirmDialog}
      <HostPickerDialog
        open={moving}
        onOpenChange={setMoving}
        options={listHostOptions(snapshot, hostPath)}
        onPick={(target) => {
          setMoving(false);
          void guard(async () => {
            await moveDoc(relPath, target);
            onRelocated("");
          }, "Document moved.");
        }}
      />
    </div>
  );
};
