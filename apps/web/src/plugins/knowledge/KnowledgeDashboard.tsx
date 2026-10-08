import { BookOpen, FileText, NotebookPen } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import type { ReferenceSummary } from "@/api/generated/models/ReferenceSummary";
import { EmptyState } from "@/app/components/entity";
import { Input } from "@/components/ui/input";
import { WorkbenchAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import { KNOWLEDGE_CLASSES, type KnowledgeClass, knowledgeClassOf } from "./knowledgeClass";
import { isTexDocument } from "./texDocument";

export const KnowledgeDashboard = ({
  notes,
  references,
  onOpen,
}: {
  notes: NoteSummary[];
  references: ReferenceSummary[];
  onOpen: (relPath: string) => void;
}): JSX.Element => {
  const [query, setQuery] = useState("");
  const [of, setOf] = useState<KnowledgeClass | null>(null);

  const counts = useMemo(() => {
    const next: Record<KnowledgeClass, number> = {
      Note: 0,
      Literature: 0,
      Report: 0,
      Finding: 0,
      Plan: 0,
      Observation: 0,
    };
    for (const note of notes) {
      if (isTexDocument(note.relPath)) continue;
      next[knowledgeClassOf(note)] += 1;
    }
    return next;
  }, [notes]);

  const needle = query.trim().toLowerCase();
  const rows = useMemo(() => {
    return notes.filter((note) => {
      if (isTexDocument(note.relPath)) {
        if (of !== null) return false;
      } else if (of && knowledgeClassOf(note) !== of) {
        return false;
      }
      if (!needle) return true;
      const hay =
        `${note.name} ${note.relPath} ${note.excerpt} ${(note.tags ?? []).join(" ")}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [notes, of, needle]);

  if (notes.length === 0 && references.length === 0) {
    return (
      <EmptyState
        icon={<BookOpen className="h-6 w-6" />}
        title="No knowledge yet"
        description="Notes, findings, plans, reports, literature, and observations appear here."
      />
    );
  }

  return (
    <div className="space-y-6">
      <section>
        <div className="grid grid-cols-2 gap-px border-y border-border bg-border sm:grid-cols-3 lg:grid-cols-6">
          {KNOWLEDGE_CLASSES.map((cls) => {
            const active = of === cls;
            return (
              <WorkbenchAction
                key={cls}
                kind="ghost"
                size="content"
                type="button"
                aria-pressed={active}
                onClick={() => setOf(active ? null : cls)}
                className={cn(
                  "flex flex-col items-start gap-1 bg-background px-3 py-3 text-left hover:bg-muted/40",
                  active && "bg-muted/50",
                )}
              >
                <span className="text-micro uppercase tracking-wide text-muted-foreground">
                  {cls}
                </span>
                <span className="font-mono text-title tabular-nums text-foreground">
                  {counts[cls]}
                </span>
              </WorkbenchAction>
            );
          })}
        </div>
      </section>

      <section className="space-y-2">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter by title, path, or tag…"
          aria-label="Filter knowledge"
          className="h-control-comfortable"
        />
        <p className="text-micro text-muted-foreground">
          {rows.length} document{rows.length === 1 ? "" : "s"}
          {of ? ` · ${of}` : ""}
        </p>
        {rows.length === 0 ? (
          <p className="text-body-lg text-muted-foreground">Nothing matches.</p>
        ) : (
          <ul className="divide-y divide-border/50 border-y border-border/60">
            {rows.map((note) => {
              const tex = isTexDocument(note.relPath);
              const cls = tex ? "TeX" : knowledgeClassOf(note);
              const Icon = tex || cls === "Literature" ? FileText : NotebookPen;
              return (
                <li key={note.relPath}>
                  <WorkbenchAction
                    kind="ghost"
                    size="content"
                    type="button"
                    onClick={() => onOpen(note.relPath)}
                    className="flex w-full items-start gap-3 px-3 py-3 text-left hover:bg-muted/40"
                  >
                    <Icon className="mt-1 size-icon flex-none text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline gap-2">
                        <span className="truncate text-body-lg font-medium text-foreground">
                          {note.name}
                        </span>
                        <span className="flex-none text-micro uppercase tracking-wide text-muted-foreground">
                          {cls}
                        </span>
                      </span>
                      <span className="block truncate text-label text-muted-foreground">
                        {note.excerpt.replace(/\n+/g, " ").trim() || note.relPath}
                      </span>
                    </span>
                  </WorkbenchAction>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
};
