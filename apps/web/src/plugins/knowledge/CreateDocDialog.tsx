import {
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "@molcrafts/ui";
import { type JSX, useEffect, useMemo, useRef, useState } from "react";
import type { DocCreateRequest } from "@/api/generated/models/DocCreateRequest";
import { DocSource } from "@/api/generated/models/DocSource";
import { ChoiceToggle } from "@/app/components/entity";
import { AppDialog } from "@/components/dialog/AppDialog";
import {
  citesRun,
  DOC_RECORD,
  DOC_SKELETON,
  fillSkeleton,
  type HostRun,
  toHtmlBody,
} from "./docTemplates";
import { KNOWLEDGE_CLASSES, type KnowledgeClass, knowledgeClassOf } from "./knowledgeClass";
import { PlanningFields } from "./PlanningFields";
import {
  buildPlanningRecord,
  emptyPlanningDraft,
  isPlanningClass,
  type PlanningDraft,
} from "./planningModel";
import { useKnowledgeListQuery } from "./queries";

export type DocFormat = "md" | "html";

export interface CreateDocInput {
  name: string;
  /** Stored as `<slug>.md` (frontmatter + markdown) or `<slug>.html` (L10). */
  format: DocFormat;
  cls: DocCreateRequest.cls;
  body: string;
  sources?: { kind: DocSource.kind; ref: string }[];
  record?: Record<string, unknown> | null;
  title?: string;
  authors?: string[];
  year?: number;
  doi?: string;
  venue?: string;
  url?: string;
}

/** The field a validation message belongs under. */
type ErrorField = "name" | "source" | "plan" | "delegation" | "year";

interface FieldErrorState {
  field: ErrorField;
  message: string;
}

const FieldError = ({
  error,
  field,
}: {
  error: FieldErrorState | null;
  field: ErrorField;
}): JSX.Element | null =>
  error?.field === field ? (
    <p className="flex items-center gap-1 text-label text-status-failed-foreground" role="alert">
      {error.message}
    </p>
  ) : null;

export const CreateDocDialog = ({
  open,
  runs,
  busy = false,
  error = null,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  runs: HostRun[];
  busy?: boolean;
  error?: string | null;
  onOpenChange: (open: boolean) => void;
  onSubmit: (input: CreateDocInput) => Promise<void>;
}): JSX.Element => {
  const listQuery = useKnowledgeListQuery();
  const plans = useMemo(
    () => (listQuery.data?.notes ?? []).filter((note) => knowledgeClassOf(note) === "Plan"),
    [listQuery.data],
  );
  const [cls, setCls] = useState<KnowledgeClass>("Note");
  const [name, setName] = useState("");
  const [format, setFormat] = useState<DocFormat>("md");
  const [body, setBody] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  const [planRef, setPlanRef] = useState("");
  const [draft, setDraft] = useState<PlanningDraft>(emptyPlanningDraft);
  const [goal, setGoal] = useState("");
  const [scope, setScope] = useState("");
  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState("");
  const [year, setYear] = useState("");
  const [doi, setDoi] = useState("");
  const [venue, setVenue] = useState("");
  const [url, setUrl] = useState("");
  const [localError, setLocalError] = useState<FieldErrorState | null>(null);
  const runsRef = useRef(runs);
  runsRef.current = runs;

  useEffect(() => {
    if (!open) return;
    const list = runsRef.current;
    setCls("Note");
    setFormat("md");
    setName("");
    setBody("");
    setSourceRef(list[0]?.ref ?? "");
    setPlanRef("");
    setDraft(emptyPlanningDraft());
    setGoal("");
    setScope("");
    setTitle("");
    setAuthors("");
    setYear("");
    setDoi("");
    setVenue("");
    setUrl("");
    setLocalError(null);
  }, [open]);

  useEffect(() => {
    if (!open || planRef || plans.length === 0) return;
    setPlanRef(plans[0]?.relPath ?? "");
  }, [open, planRef, plans]);

  const runSourced = citesRun(cls);
  const planning = isPlanningClass(cls);
  const plansLoading = planning && listQuery.isPending;
  const planMissing = planning && !plansLoading && plans.length === 0;

  const submit = async (): Promise<void> => {
    const trimmed = name.trim();
    if (!trimmed) {
      setLocalError({ field: "name", message: "Name required." });
      return;
    }
    if (runSourced && !sourceRef) {
      setLocalError({ field: "source", message: "Choose a run this document records." });
      return;
    }
    if (planning && !planRef) {
      setLocalError({ field: "plan", message: "Choose the Plan this document cites." });
      return;
    }
    let record: Record<string, unknown> | undefined = DOC_RECORD[cls];
    if (planning) {
      const built = buildPlanningRecord(cls, draft);
      if (!built.ok) {
        setLocalError({ field: "plan", message: built.message });
        return;
      }
      record = built.record;
    }
    if (cls === "Delegation") {
      const goalText = goal.trim();
      const scopeText = scope.trim();
      if (!goalText || !scopeText) {
        setLocalError({ field: "delegation", message: "A delegation needs a goal and a scope." });
        return;
      }
      record = { goal: goalText, scope: scopeText };
    }
    const yearNumber = year.trim() ? Number(year) : undefined;
    if (year.trim() && !Number.isInteger(yearNumber)) {
      setLocalError({ field: "year", message: "Year must be a whole number." });
      return;
    }
    setLocalError(null);
    const authorList = authors
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const filled = fillSkeleton(body, {
      sourceRef: runSourced ? sourceRef : null,
      citation:
        cls === "Literature"
          ? {
              title: title.trim(),
              authors: authorList.join(", "),
              year: year.trim(),
              venue: venue.trim(),
              doi: doi.trim(),
              url: url.trim(),
            }
          : undefined,
    });
    await onSubmit({
      name: trimmed,
      cls: cls as DocCreateRequest.cls,
      format,
      body: format === "html" ? toHtmlBody(filled) : filled,
      ...(runSourced ? { sources: [{ kind: DocSource.kind.RUN, ref: sourceRef }] } : {}),
      ...(planning ? { sources: [{ kind: DocSource.kind.FILE, ref: planRef }] } : {}),
      ...(record ? { record } : {}),
      ...(cls === "Literature"
        ? {
            title: title.trim() || undefined,
            authors: authorList.length > 0 ? authorList : undefined,
            year: yearNumber,
            doi: doi.trim() || undefined,
            venue: venue.trim() || undefined,
            url: url.trim() || undefined,
          }
        : {}),
    });
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title="New document"
      // Several fields per class: ↵ must not create a half-filled document.
      submitOnEnter={false}
      size="wide"
      primaryLabel="Create document"
      busyLabel="Creating…"
      busy={busy}
      primaryDisabled={(runSourced && runs.length === 0) || planMissing}
      onPrimary={submit}
      error={error}
    >
      <div className="grid gap-3">
        <div className="grid gap-2">
          <Label htmlFor="doc-class">Class</Label>
          <Select
            value={cls}
            onValueChange={(value) => {
              const next = value as KnowledgeClass;
              setCls(next);
              setBody(DOC_SKELETON[next]);
              setLocalError(null);
            }}
          >
            <SelectTrigger id="doc-class">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KNOWLEDGE_CLASSES.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <Label>Format</Label>
          <ChoiceToggle
            label="Format"
            value={format}
            choices={[
              { value: "md", label: "Markdown" },
              { value: "html", label: "HTML" },
            ]}
            onChange={setFormat}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="doc-name">Name</Label>
          <Input
            id="doc-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Tg result"
            disabled={busy}
          />
          <FieldError error={localError} field="name" />
        </div>
        {runSourced && (
          <div className="grid gap-2">
            <Label htmlFor="doc-source">Source run</Label>
            {runs.length === 0 ? (
              <p className="text-label text-muted-foreground">This host has no run to cite yet.</p>
            ) : (
              <Select value={sourceRef} onValueChange={setSourceRef}>
                <SelectTrigger id="doc-source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {runs.map((run) => (
                    <SelectItem key={run.ref} value={run.ref}>
                      {run.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <FieldError error={localError} field="source" />
          </div>
        )}
        {isPlanningClass(cls) && (
          <div className="grid gap-2">
            <Label htmlFor="doc-plan">Plan</Label>
            {plansLoading ? (
              <p className="text-label text-muted-foreground">Loading plans…</p>
            ) : planMissing ? (
              <p className="text-label text-muted-foreground">
                Write a Plan first. A roadmap, todo, or milestone cites one.
              </p>
            ) : (
              <Select value={planRef} onValueChange={setPlanRef}>
                <SelectTrigger id="doc-plan">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {plans.map((plan) => (
                    <SelectItem key={plan.relPath} value={plan.relPath}>
                      {plan.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <PlanningFields cls={cls} draft={draft} disabled={busy} onChange={setDraft} />
            <FieldError error={localError} field="plan" />
          </div>
        )}
        {cls === "Delegation" && (
          <div className="grid gap-2">
            <Label htmlFor="doc-goal">Goal</Label>
            <Input
              id="doc-goal"
              value={goal}
              disabled={busy}
              onChange={(event) => setGoal(event.target.value)}
            />
            <Label htmlFor="doc-scope">Scope</Label>
            <Input
              id="doc-scope"
              value={scope}
              disabled={busy}
              onChange={(event) => setScope(event.target.value)}
            />
            <FieldError error={localError} field="delegation" />
          </div>
        )}
        {cls === "Literature" && (
          <div className="grid gap-2">
            <Label htmlFor="doc-title">Title</Label>
            <Input
              id="doc-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
            <Label htmlFor="doc-authors">Authors</Label>
            <Input
              id="doc-authors"
              value={authors}
              onChange={(event) => setAuthors(event.target.value)}
              placeholder="Lin, Chen"
            />
            <Label htmlFor="doc-year">Year</Label>
            <Input
              id="doc-year"
              value={year}
              onChange={(event) => setYear(event.target.value)}
              inputMode="numeric"
            />
            <FieldError error={localError} field="year" />
            <Label htmlFor="doc-doi">DOI</Label>
            <Input id="doc-doi" value={doi} onChange={(event) => setDoi(event.target.value)} />
            <Label htmlFor="doc-venue">Venue</Label>
            <Input
              id="doc-venue"
              value={venue}
              onChange={(event) => setVenue(event.target.value)}
            />
            <Label htmlFor="doc-url">URL</Label>
            <Input id="doc-url" value={url} onChange={(event) => setUrl(event.target.value)} />
          </div>
        )}
        <div className="grid gap-2">
          <Label htmlFor="doc-body">Body</Label>
          <Textarea
            id="doc-body"
            value={body}
            rows={6}
            onChange={(event) => setBody(event.target.value)}
            disabled={busy}
          />
        </div>
      </div>
    </AppDialog>
  );
};
