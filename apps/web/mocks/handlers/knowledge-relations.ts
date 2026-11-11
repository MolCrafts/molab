/** Offline relation authoring mutates the same narrative used by graph reads. */
import { HttpResponse, http } from "msw";
import { KnowledgeGraphEdge } from "@/api/generated/models/KnowledgeGraphEdge";
import type { DocRelations, DocRelationUpdate } from "@/api/knowledge";
import { dirname } from "@/lib/workspace-path";
import { showcaseKnowledgeEdges, showcaseKnowledgeLinks } from "./knowledge-links";
import { workspaceRoute } from "./workspaceRoute";

interface RelationMockNote {
  relPath: string;
  body: string;
  links: string[];
  excerpt?: string;
}

const digest = async (note: RelationMockNote): Promise<string> => {
  const bytes = new TextEncoder().encode(JSON.stringify(note));
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
};
const problem = (detail: string, status = 422) => HttpResponse.json({ detail }, { status });
const roles = new Set<string>(Object.values(KnowledgeGraphEdge.role));

export const createKnowledgeRelationHandlers = <T extends RelationMockNote>(
  notes: Map<string, T>,
  onWrite: (path: string, body: string) => void,
) => {
  let pendingWrite = Promise.resolve();
  const snapshot = async (note: T): Promise<DocRelations> => {
    const relations = showcaseKnowledgeLinks(note, notes).map(
      ({ id, target, role, label, kind }) => ({ id, target, role, label, kind }),
    );
    return { relPath: note.relPath, digest: await digest(note), relations };
  };
  return [
    http.get(workspaceRoute("/api/knowledge/doc/relations"), async ({ request }) => {
      await pendingWrite;
      const path = new URL(request.url).searchParams.get("path") ?? "";
      const note = notes.get(path);
      return note ? HttpResponse.json(await snapshot(note)) : problem("Note not found", 404);
    }),
    http.patch(workspaceRoute("/api/knowledge/doc/relations"), async ({ request }) => {
      const path = new URL(request.url).searchParams.get("path") ?? "";
      const payload = (await request.json()) as DocRelationUpdate;
      const change = pendingWrite.then(async () => {
        const note = notes.get(path);
        if (!note) return problem("Note not found", 404);
        if (!payload.ifMatch) return problem("ifMatch is required");
        if (payload.ifMatch !== (await digest(note)))
          return problem("Document changed since it was read", 409);
        if (payload.action !== "remove" && !roles.has(payload.role))
          return problem("Invalid relation role");
        if (payload.action === "add") {
          const target = payload.target;
          if (!target || /[()\r\n]/.test(target) || /[[\]\r\n]/.test(payload.text ?? "")) {
            return problem("Invalid relation target or label");
          }
          let rawTarget = target;
          if (target.startsWith("molab:")) {
            if (
              !/^molab:(?:project\/[^/]+|asset\/[^/]+|experiment\/[^/]+(?:\/run\/[^/]+(?:\/execution\/[^/]+)?)?)$/.test(
                target,
              )
            ) {
              return problem("Invalid molab reference");
            }
          } else if (!/^https?:\/\//.test(target)) {
            if (target.startsWith("/") || target.split("/").includes("..") || !notes.has(target)) {
              return problem("Target must be an existing workspace document");
            }
            const from = dirname(path).split("/").filter(Boolean);
            const to = target.split("/");
            while (from.length && to.length && from[0] === to[0]) {
              from.shift();
              to.shift();
            }
            rawTarget = [...from.map(() => ".."), ...to].join("/");
          }
          if (
            /^https?:\/\//.test(target) &&
            !["cites", "derived_from", "references"].includes(payload.role)
          ) {
            return problem("Unsupported web relation role");
          }
          const label = payload.text || target.split("/").pop() || target;
          if (
            payload.role === "references" &&
            /^@(\w+)(?: |$)/.test(label) &&
            roles.has(label.slice(1).split(" ")[0])
          ) {
            return problem("A reference label cannot begin with a typed relation sigil");
          }
          const encoded = payload.role === "references" ? label : `@${payload.role} ${label}`;
          const prefix = note.body && !note.body.endsWith("\n") ? `${note.body}\n` : note.body;
          const line = `- [${encoded}](${rawTarget})\n`;
          note.body =
            prefix +
            (path.endsWith(".html") ? `<molab-markdown>\n${line}</molab-markdown>\n` : line);
        } else if (payload.action === "replace" || payload.action === "remove") {
          const link = showcaseKnowledgeLinks(note, notes).find((entry) => entry.id === payload.id);
          if (!link) return problem("Relation occurrence no longer exists");
          if (payload.action === "replace") {
            if (
              link.kind === "external" &&
              !["cites", "derived_from", "references"].includes(payload.role)
            ) {
              return problem("Unsupported web relation role");
            }
            const encoded =
              payload.role === "references" ? link.label : `@${payload.role} ${link.label}`;
            note.body =
              note.body.slice(0, link.labelStart) + encoded + note.body.slice(link.labelEnd);
          } else {
            const start = note.body.lastIndexOf("\n", link.start - 1) + 1;
            const nextLine = note.body.indexOf("\n", link.end);
            const end = nextLine < 0 ? note.body.length : nextLine;
            if (
              /^[ \t]*(?:[-+*]|\d+[.)])[ \t]+$/.test(note.body.slice(start, link.start)) &&
              !note.body.slice(link.end, end).trim()
            ) {
              note.body =
                note.body.slice(0, start) + note.body.slice(Math.min(end + 1, note.body.length));
            } else {
              note.body = note.body.slice(0, link.start) + link.label + note.body.slice(link.end);
            }
          }
        } else return problem("Invalid relation action");
        note.excerpt = note.body.slice(0, 160);
        note.links = showcaseKnowledgeEdges(notes)
          .filter((edge) => edge.source === path)
          .map((edge) => edge.target);
        onWrite(path, note.body);
        return HttpResponse.json(await snapshot(note));
      });
      pendingWrite = change.then(
        () => undefined,
        () => undefined,
      );
      return change;
    }),
  ];
};
