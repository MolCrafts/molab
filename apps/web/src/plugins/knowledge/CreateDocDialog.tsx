import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "@molcrafts/ui";
import { Check } from "lucide-react";
import { type JSX, useEffect, useMemo, useRef, useState } from "react";
import type { DocCreateRequest } from "@/api/generated/models/DocCreateRequest";
import { DocSource } from "@/api/generated/models/DocSource";
import { WorkbenchAction } from "@/components/workbench";
import { citesRun, DOC_SKELETON, type HostRun } from "./docTemplates";
import { KNOWLEDGE_CLASSES, type KnowledgeClass, knowledgeClassOf } from "./knowledgeClass";
import { PlanningFields } from "./PlanningFields";
import {
  buildPlanningRecord,
  emptyPlanningDraft,
  isPlanningClass,
  type PlanningDraft,
} from "./planningModel";
import { useKnowledgeListQuery } from "./queries";

export interface CreateDocInput {
  name: string;
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
  const [localError, setLocalError] = useState<string | null>(null);
  const runsRef = useRef(runs);
  runsRef.current = runs;

  useEffect(() => {
    if (!open) return;
    const list = runsRef.current;
    setCls("Note");
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
  const message = localError ?? error;
  const plansLoading = planning && listQuery.isPending;
  const planMissing = planning && !plansLoading && plans.length === 0;

  const submit = async (): Promise<void> => {
    const trimmed = name.trim();
    if (!trimmed) {
      setLocalError("Name required.");
      return;
    }
    if (runSourced && !sourceRef) {
      setLocalError("Choose a run this document records.");
      return;
    }
    if (planning && !planRef) {
      setLocalError("Choose the Plan this document cites.");
      return;
    }
    let record: Record<string, unknown> | undefined;
    if (planning) {
      const built = buildPlanningRecord(cls, draft);
      if (!built.ok) {
        setLocalError(built.message);
        return;
      }
      record = built.record;
    }
    if (cls === "Delegation") {
      const goalText = goal.trim();
      const scopeText = scope.trim();
      if (!goalText || !scopeText) {
        setLocalError("A delegation needs a goal and a scope.");
        return;
      }
      record = { goal: goalText, scope: scopeText };
    }
    const yearNumber = year.trim() ? Number(year) : undefined;
    if (year.trim() && !Number.isInteger(yearNumber)) {
      setLocalError("Year must be a whole number.");
      return;
    }
    setLocalError(null);
    const authorList = authors
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    await onSubmit({
      name: trimmed,
      cls: cls as DocCreateRequest.cls,
      body,
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[min(85vh,48rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>New document</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 py-1">
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
            <Label htmlFor="doc-name">Name</Label>
            <Input
              id="doc-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Tg result"
              disabled={busy}
            />
          </div>
          {runSourced && (
            <div className="grid gap-2">
              <Label htmlFor="doc-source">Source run</Label>
              {runs.length === 0 ? (
                <p className="text-label text-muted-foreground">
                  This host has no run to cite yet.
                </p>
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
          {message && <p className="text-body-lg text-destructive">{message}</p>}
        </div>
        <DialogFooter>
          <WorkbenchAction
            icon={<Check aria-hidden />}
            aria-busy={busy}
            kind="primary"
            type="button"
            disabled={busy || (runSourced && runs.length === 0) || planMissing}
            onClick={() => void submit()}
          >
            {busy ? "Creating…" : "Create"}
          </WorkbenchAction>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
