/** Non-modal sync form anchored to a file-tree row. */

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Clock } from "lucide-react";
import { type JSX, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { WorkbenchAction, WorkbenchDismissAction } from "@/components/workbench";
import { reportStatus } from "@/lib/status-report";
import { cn } from "@/lib/utils";
import {
  deleteSyncRule,
  previewSyncRule,
  runSyncRule,
  type SyncContent,
  type SyncFileType,
  type SyncRule,
  type SyncWhen,
  saveSyncRule,
  syncRuleKeys,
} from "./syncRules";

const FILE_TYPES: { id: SyncFileType; label: string }[] = [
  { id: "py", label: "Python" },
  { id: "json", label: "JSON" },
  { id: "md", label: "Markdown" },
  { id: "images", label: "Images" },
  { id: "logs", label: "Logs" },
];

const statusLabel = (status: string | null): string => {
  if (status === "ok") return "Succeeded";
  if (status === "error") return "Failed";
  if (status === "skipped") return "Skipped";
  return status ?? "";
};

const timeLabel = (value: string | null): string => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

export const syncMarkLabel = (when: SyncWhen, intervalMinutes: number): string => {
  if (when === "on-open") return "Syncs when this workspace opens";
  if (when === "interval") return `Syncs every ${intervalMinutes} minutes`;
  return "Syncs when you ask";
};

export const SyncMark = ({
  when,
  intervalMinutes,
}: {
  when: SyncWhen;
  intervalMinutes: number;
}): JSX.Element => {
  const label = syncMarkLabel(when, intervalMinutes);
  const Icon = when === "manual" ? ArrowRight : Clock;
  return (
    <span role="img" title={label} aria-label={label} className="inline-flex text-muted-foreground">
      <Icon className="size-icon-sm" aria-hidden />
    </span>
  );
};

interface Draft {
  direction: "pull" | "push";
  content: SyncContent;
  types: SyncFileType[];
  extraFiles: "keep" | "remove";
  when: SyncWhen;
  minutes: number;
}

interface SyncRuleFormProps {
  nodeId: string;
  name: string;
  relativePath: string;
  kind: "file" | "directory";
  rule: SyncRule | null;
  rulesLoading: boolean;
  onClose: () => void;
  onSynced: () => void;
}

const Choice = ({
  name,
  value,
  checked,
  label,
  detail,
  onSelect,
}: {
  name: string;
  value: string;
  checked: boolean;
  label: string;
  detail?: string;
  onSelect: () => void;
}): JSX.Element => (
  <label className="flex items-start gap-2">
    <input
      type="radio"
      className="mt-1"
      name={name}
      value={value}
      checked={checked}
      onChange={onSelect}
    />
    <span>
      <span className="block">{label}</span>
      {detail ? <span className="block text-micro text-muted-foreground">{detail}</span> : null}
    </span>
  </label>
);

export const SyncRuleForm = ({
  nodeId,
  name,
  relativePath,
  kind,
  rule,
  rulesLoading,
  onClose,
  onSynced,
}: SyncRuleFormProps): JSX.Element => {
  const queryClient = useQueryClient();
  const panelRef = useRef<HTMLFormElement>(null);
  const dirty = useRef(false);
  const [placed, setPlaced] = useState(false);
  const [direction, setDirection] = useState<Draft["direction"]>(rule?.direction ?? "pull");
  const [content, setContent] = useState<SyncContent>(rule?.content ?? "everything");
  const [types, setTypes] = useState<SyncFileType[]>(rule?.types ?? []);
  const [extraFiles, setExtraFiles] = useState<Draft["extraFiles"]>(rule?.extraFiles ?? "keep");
  const [when, setWhen] = useState<SyncWhen>(rule?.when ?? "manual");
  const [minutes, setMinutes] = useState(rule?.intervalMinutes ?? 15);
  const [ruleId, setRuleId] = useState<string | null>(rule?.id ?? null);
  const [last, setLast] = useState<Pick<SyncRule, "lastRunAt" | "lastStatus" | "lastOutput">>({
    lastRunAt: rule?.lastRunAt ?? null,
    lastStatus: rule?.lastStatus ?? null,
    lastOutput: rule?.lastOutput ?? null,
  });
  const [error, setError] = useState("");
  const [preview, setPreview] = useState("");
  const [running, setRunning] = useState(false);
  const folder = kind === "directory";

  const draft = (): Draft => ({ direction, content, types, extraFiles, when, minutes });

  useEffect(() => {
    if (!rule || dirty.current) return;
    setDirection(rule.direction);
    setContent(rule.content);
    setTypes(rule.types);
    setExtraFiles(rule.extraFiles);
    setWhen(rule.when);
    setMinutes(rule.intervalMinutes);
    setRuleId(rule.id);
    setLast(rule);
  }, [rule]);

  useLayoutEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const place = (): void => {
      const row = document.querySelector(`[data-tree-id="${CSS.escape(nodeId)}"]`);
      const width = panel.offsetWidth;
      const height = panel.offsetHeight;
      const bounds = row?.getBoundingClientRect();
      let left = bounds ? bounds.right + 8 : Math.max(8, window.innerWidth - width - 8);
      let top = bounds ? bounds.top : 8;
      if (left + width > window.innerWidth - 8) {
        left = Math.max(8, (bounds?.left ?? window.innerWidth) - width - 8);
      }
      if (top + height > window.innerHeight - 8) {
        top = Math.max(8, window.innerHeight - height - 8);
      }
      panel.style.top = `${top}px`;
      panel.style.left = `${left}px`;
      setPlaced(true);
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(panel);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [nodeId]);

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  useEffect(() => {
    const onPointer = (event: PointerEvent): void => {
      if (!panelRef.current?.contains(event.target as Node)) onClose();
    };
    window.addEventListener("pointerdown", onPointer);
    return () => window.removeEventListener("pointerdown", onPointer);
  }, [onClose]);

  const fail = (message: string): null => {
    setError(message);
    reportStatus(message, "error");
    return null;
  };

  const commit = async (next: Draft): Promise<SyncRule | null> => {
    dirty.current = true;
    setDirection(next.direction);
    setContent(next.content);
    setTypes(next.types);
    setExtraFiles(next.extraFiles);
    setWhen(next.when);
    setMinutes(next.minutes);
    if (folder && next.content === "types" && next.types.length === 0) {
      return fail("Select at least one file type.");
    }
    if (next.when === "interval" && next.minutes < 5) {
      return fail("Interval must be at least 5 minutes.");
    }
    setError("");
    try {
      const saved = await saveSyncRule({
        path: relativePath,
        kind,
        direction: next.direction,
        content: folder ? next.content : "everything",
        types: folder && next.content === "types" ? next.types : [],
        extraFiles: folder ? next.extraFiles : "keep",
        when: next.when,
        intervalMinutes: next.minutes >= 5 ? next.minutes : 15,
      });
      setRuleId(saved.id);
      setLast(saved);
      await queryClient.invalidateQueries({ queryKey: syncRuleKeys.all });
      return saved;
    } catch (caught) {
      return fail(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const syncNow = async (): Promise<void> => {
    if (running) return;
    const saved = await commit(draft());
    if (!saved) return;
    setRunning(true);
    reportStatus(`Syncing ${name}…`, "info", 0);
    try {
      const result = await runSyncRule(saved.id);
      setLast(result.rule);
      setPreview(result.output);
      reportStatus(`Synced ${name}`, "success");
      await queryClient.invalidateQueries({ queryKey: syncRuleKeys.all });
      onSynced();
    } catch (caught) {
      fail(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunning(false);
    }
  };

  const previewNow = async (): Promise<void> => {
    if (running) return;
    const saved = await commit(draft());
    if (!saved) return;
    setRunning(true);
    reportStatus(`Previewing ${name}…`, "info", 0);
    try {
      const result = await previewSyncRule(saved.id);
      setPreview(result.output);
      reportStatus(`Preview of ${name} is ready`, "success");
    } catch (caught) {
      fail(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunning(false);
    }
  };

  const remove = async (): Promise<void> => {
    if (!ruleId || running) return;
    setRunning(true);
    try {
      await deleteSyncRule(ruleId);
      await queryClient.invalidateQueries({ queryKey: syncRuleKeys.all });
      onClose();
    } catch (caught) {
      fail(caught instanceof Error ? caught.message : String(caught));
      setRunning(false);
    }
  };

  const noun = folder ? "folder" : "file";

  return createPortal(
    <form
      ref={panelRef}
      tabIndex={-1}
      aria-label={`Sync ${name}`}
      className={cn(
        "fixed z-40 w-80 max-h-[min(32rem,calc(100vh-1rem))] overflow-auto rounded-md border border-border bg-popover p-3 text-popover-foreground shadow-md outline-none",
        placed ? "visible" : "invisible",
      )}
      onSubmit={(event) => {
        event.preventDefault();
        void syncNow();
      }}
      onKeyDown={(event) => {
        event.stopPropagation();
        if (event.key === "Escape") {
          event.preventDefault();
          onClose();
        }
      }}
      onContextMenu={(event) => event.stopPropagation()}
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-micro text-muted-foreground">Sync</p>
          <h2 className="truncate text-body" title={name}>
            {name}
          </h2>
        </div>
        <WorkbenchDismissAction label="Close sync" onClick={onClose} />
      </div>
      <fieldset disabled={rulesLoading || running} className="min-w-0 space-y-3 border-0 p-0">
        <p className="break-all font-mono text-micro text-muted-foreground">
          {relativePath || "(workspace root)"}
        </p>
        <fieldset className="space-y-2 border-0 p-0">
          <legend className="mb-1 text-micro text-muted-foreground">Direction</legend>
          <Choice
            name="sync-direction"
            value="pull"
            checked={direction === "pull"}
            label="Bring here"
            detail={`Copies this ${noun} into the local mirror. Later opens read that copy.`}
            onSelect={() => void commit({ ...draft(), direction: "pull" })}
          />
          <Choice
            name="sync-direction"
            value="push"
            checked={direction === "push"}
            label="Send there"
            detail="Writes the local mirror back. This changes the remote copy."
            onSelect={() => void commit({ ...draft(), direction: "push" })}
          />
        </fieldset>
        {folder ? (
          <fieldset className="space-y-2 border-0 p-0">
            <legend className="mb-1 text-micro text-muted-foreground">What to copy</legend>
            <Choice
              name="sync-content"
              value="everything"
              checked={content === "everything"}
              label="Everything"
              onSelect={() => void commit({ ...draft(), content: "everything" })}
            />
            <Choice
              name="sync-content"
              value="records"
              checked={content === "records"}
              label="Records and notes"
              detail="JSON, Markdown, text, and YAML."
              onSelect={() => void commit({ ...draft(), content: "records" })}
            />
            <Choice
              name="sync-content"
              value="code"
              checked={content === "code"}
              label="Code"
              detail="Python and workflow files."
              onSelect={() => void commit({ ...draft(), content: "code" })}
            />
            <Choice
              name="sync-content"
              value="skip-bulk"
              checked={content === "skip-bulk"}
              label="Skip bulk products"
              detail="Skips out/, checkpoints/, and large trajectory files."
              onSelect={() => void commit({ ...draft(), content: "skip-bulk" })}
            />
            <Choice
              name="sync-content"
              value="types"
              checked={content === "types"}
              label="Selected types"
              onSelect={() => void commit({ ...draft(), content: "types" })}
            />
            {content === "types" ? (
              <div className="space-y-1 pl-5">
                {FILE_TYPES.map((type) => (
                  <label key={type.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={types.includes(type.id)}
                      onChange={() => {
                        const nextTypes = types.includes(type.id)
                          ? types.filter((item) => item !== type.id)
                          : [...types, type.id];
                        void commit({ ...draft(), content: "types", types: nextTypes });
                      }}
                    />
                    <span>{type.label}</span>
                  </label>
                ))}
              </div>
            ) : null}
          </fieldset>
        ) : null}
        {folder ? (
          <fieldset className="space-y-2 border-0 p-0">
            <legend className="mb-1 text-micro text-muted-foreground">
              Files only on one side
            </legend>
            <Choice
              name="sync-extra"
              value="keep"
              checked={extraFiles === "keep"}
              label="Keep"
              onSelect={() => void commit({ ...draft(), extraFiles: "keep" })}
            />
            <Choice
              name="sync-extra"
              value="remove"
              checked={extraFiles === "remove"}
              label="Remove files the source does not have"
              onSelect={() => void commit({ ...draft(), extraFiles: "remove" })}
            />
          </fieldset>
        ) : null}
        <fieldset className="space-y-2 border-0 p-0">
          <legend className="mb-1 text-micro text-muted-foreground">When</legend>
          <Choice
            name="sync-when"
            value="manual"
            checked={when === "manual"}
            label="Manual"
            detail="Only when you choose Sync now."
            onSelect={() => void commit({ ...draft(), when: "manual" })}
          />
          <Choice
            name="sync-when"
            value="on-open"
            checked={when === "on-open"}
            label="When this workspace opens"
            detail="Once, after this serve connects."
            onSelect={() => void commit({ ...draft(), when: "on-open" })}
          />
          <div className="flex items-start gap-2">
            <input
              type="radio"
              className="mt-1"
              name="sync-when"
              value="interval"
              checked={when === "interval"}
              aria-labelledby="sync-when-interval"
              onChange={() => void commit({ ...draft(), when: "interval" })}
            />
            <div>
              <span id="sync-when-interval" className="block">
                Every
              </span>
              <span className="mt-1 flex items-center gap-2">
                <input
                  type="number"
                  min={5}
                  step={1}
                  aria-label="Minutes between syncs"
                  className="h-control-compact w-16 rounded-hairline border border-border bg-background px-2 font-mono text-body"
                  value={minutes}
                  onChange={(event) => {
                    const parsed = Number(event.target.value);
                    if (Number.isFinite(parsed)) setMinutes(parsed);
                  }}
                  onBlur={(event) => {
                    const parsed = Number(event.target.value);
                    const nextMinutes = Number.isFinite(parsed) ? parsed : minutes;
                    if (when === "interval") void commit({ ...draft(), minutes: nextMinutes });
                  }}
                />
                <span>minutes</span>
              </span>
              <span className="block text-micro text-muted-foreground">
                While this serve is running. At least 5 minutes.
              </span>
            </div>
          </div>
        </fieldset>
        {last.lastRunAt ? (
          <p className="text-micro text-muted-foreground">
            Last sync {timeLabel(last.lastRunAt)} · {statusLabel(last.lastStatus)}
            {last.lastOutput ? ` · ${last.lastOutput}` : ""}
          </p>
        ) : null}
        {error ? <p className="text-micro text-destructive">{error}</p> : null}
        <div className="flex gap-2">
          <WorkbenchAction type="button" kind="secondary" onClick={() => void previewNow()}>
            Preview
          </WorkbenchAction>
          <WorkbenchAction type="submit" kind="primary">
            Sync now
          </WorkbenchAction>
        </div>
        {preview ? (
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap font-mono text-micro">
            {preview}
          </pre>
        ) : null}
        {ruleId ? (
          <WorkbenchAction type="button" kind="danger" onClick={() => void remove()}>
            Remove rule
          </WorkbenchAction>
        ) : null}
      </fieldset>
    </form>,
    document.body,
  );
};
