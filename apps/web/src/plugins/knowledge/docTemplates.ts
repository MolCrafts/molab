import { runLabel } from "@/app/runs/runTitle";
import { formatComponent, parseAttrs } from "./doc/blocks";
import type { KnowledgeClass } from "./knowledgeClass";
import { isPlanningClass } from "./planningModel";

/**
 * The starting body of each class (L10 v3 templates): the MkDocs blocks and
 * `<molab-…>` components its page is made of. The page title is the document
 * name, so a skeleton has no `# Title`. `fillSkeleton` completes the
 * component lines the create form knows the answer to.
 */
export const DOC_SKELETON: Record<KnowledgeClass, string> = {
  Note: "",
  Literature: [
    "::molab-citation",
    "",
    '??? abstract "Abstract"',
    "    Paste the abstract.",
    "",
    "## Key points",
    "",
    "- ",
    "",
    "## Notes",
    "",
  ].join("\n"),
  Report: [
    '!!! failure "What failed"',
    "    One sentence: what failed, where, after how long.",
    "",
    "::molab-run-ref",
    "",
    "## Evidence",
    "",
    "::molab-log",
    "",
    "## Cause",
    "",
    "## Remedy",
    "",
    "- [ ] ",
    "",
  ].join("\n"),
  Finding: [
    '!!! success "Claim"',
    "    The result, as one sentence.",
    "",
    "## Evidence",
    "",
    "::molab-run-ref",
    "",
    "## Holds under",
    "",
    "## Builds on",
    "",
  ].join("\n"),
  Observation: [
    "What was seen.",
    "",
    "## Seen in",
    "",
    "::molab-run-ref",
    "",
    "## Untested",
    "",
    '!!! warning "Not yet tested"',
    "    What this has not been checked against.",
    "",
  ].join("\n"),
  Hypothesis: [
    '!!! question "Claim"',
    "    One testable claim, as one sentence.",
    "",
    "## Would support it",
    "",
    "## Would refute it",
    "",
    "## Builds on",
    "",
  ].join("\n"),
  Decision: [
    '!!! note "Decision"',
    "    What was chosen, as one sentence.",
    "",
    "## Decided by",
    "",
    "## Why",
    "",
    "## Alternatives considered",
    "",
  ].join("\n"),
  Plan: [
    '!!! abstract "Goal"',
    "    What this plan decides, in one sentence.",
    "",
    "## Roadmap",
    "",
    "::molab-stage-track",
    "",
    "## Next",
    "",
    "- [ ] ",
    "",
    "## Builds on",
    "",
  ].join("\n"),
  Roadmap: ["::molab-stage-track", "", "## Stages", "", "## Cites", ""].join("\n"),
  Todo: ["::molab-todo-list", "", "## Notes", ""].join("\n"),
  Milestone: ["::molab-milestone", "", "## Evidence so far", "", "## On the roadmap", ""].join(
    "\n",
  ),
  Delegation: [
    '!!! note "Brief"',
    "    What the agent should do, and what it should report.",
    "",
    "## Asks",
    "",
    "::molab-approval",
    "",
    "## Scope",
    "",
    "## Activity",
    "",
  ].join("\n"),
};

/**
 * The record a class starts with: a new Hypothesis has no verdict yet, and a
 * Decision written down is one already made.
 */
export const DOC_RECORD: Partial<Record<KnowledgeClass, Record<string, unknown>>> = {
  Hypothesis: { verdict: "open" },
  Decision: { status: "made" },
};

export interface SkeletonFacts {
  /** The run a sourced document cites (`molab:` ref). */
  sourceRef?: string | null;
  /** A Literature document's citation fields. */
  citation?: Partial<Record<"title" | "authors" | "year" | "venue" | "doi" | "url", string>>;
}

/** Bare component lines the form can complete: the source run, the citation. */
export const fillSkeleton = (body: string, facts: SkeletonFacts): string =>
  body
    .split("\n")
    .map((line) => {
      if (facts.sourceRef && /^::molab-(run-ref|log)\s*$/.test(line)) {
        const name = line.trim().slice(2);
        return formatComponent(
          name,
          name === "molab-log" ? { run: facts.sourceRef } : { ref: facts.sourceRef },
        );
      }
      if (facts.citation && /^::molab-citation\s*$/.test(line)) {
        const attrs = Object.fromEntries(
          Object.entries(facts.citation).filter((entry): entry is [string, string] =>
            Boolean(entry[1]),
          ),
        );
        return formatComponent("molab-citation", attrs);
      }
      return line;
    })
    .join("\n");

const SOURCED: ReadonlySet<KnowledgeClass> = new Set([
  "Report",
  "Finding",
  "Plan",
  "Roadmap",
  "Todo",
  "Milestone",
  "Observation",
  "Hypothesis",
  "Decision",
  "Delegation",
]);

export const isSourcedClass = (cls: KnowledgeClass): boolean => SOURCED.has(cls);

/** A sourced class whose source is a run. Planning documents cite a Plan instead. */
export const citesRun = (cls: KnowledgeClass): boolean =>
  isSourcedClass(cls) && !isPlanningClass(cls);

export interface HostRun {
  id: string;
  label: string;
  ref: string;
}

/** Runs that can source a document created on *hostPath*. An empty host is the workspace. */
export const runsForHost = (
  runs: { id: string; name: string; path: string; ref?: string }[],
  hostPath: string,
): HostRun[] =>
  runs.flatMap((run) => {
    if (!run.ref) return [];
    if (hostPath && run.path !== hostPath && !run.path.startsWith(`${hostPath}/`)) return [];
    return [{ id: run.id, label: runLabel(run), ref: run.ref }];
  });

const COMPONENT_LINE = /^::(molab-[a-z][a-z0-9-]*)(?:\{(.*)\})?\s*$/;

const escapeAttr = (value: string): string =>
  value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/**
 * A markdown body as the body of an HTML document (L10): prose runs wrapped in
 * `<molab-markdown>`, each component line as its element. Blank runs between
 * blocks are dropped.
 */
export const toHtmlBody = (markdown: string): string => {
  const out: string[] = [];
  let prose: string[] = [];
  const flush = (): void => {
    const text = prose.join("\n").replace(/^\n+|\n+$/g, "");
    if (text.trim()) out.push("<molab-markdown>", text, "</molab-markdown>");
    prose = [];
  };
  for (const line of markdown.split("\n")) {
    const match = line.match(COMPONENT_LINE);
    if (!match?.[1]) {
      prose.push(line);
      continue;
    }
    flush();
    const attrs = Object.entries(parseAttrs(match[2] ?? ""))
      .map(([key, value]) => ` ${key}="${escapeAttr(value)}"`)
      .join("");
    out.push(`<${match[1]}${attrs}></${match[1]}>`);
  }
  flush();
  return out.join("\n");
};
