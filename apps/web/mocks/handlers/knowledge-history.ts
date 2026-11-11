import { HttpResponse, http } from "msw";
import { workspaceRoute } from "./workspaceRoute";

/** A saved fixture is the offline counterpart of one committed file version. */
export function showcaseHistoryHandlers(notes: ReadonlyMap<string, { body: string }>) {
  const saved = new Map([...notes].map(([path, note]) => [path, note.body]));
  const commit = "a".repeat(40);
  return [
    http.get(workspaceRoute("/api/history/document"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      const path = params.get("document") ?? "";
      const version = params.get("commit");
      const body = saved.get(path);
      if (body === undefined)
        return HttpResponse.json({ detail: "Document not found" }, { status: 404 });
      if (version && version !== commit)
        return HttpResponse.json({ detail: "Version not found" }, { status: 404 });
      const current = notes.get(path)?.body ?? "";
      const before = body.split("\n");
      const after = current.split("\n");
      return HttpResponse.json({
        available: true,
        revisions: [
          {
            commit,
            occurred_at: "2026-11-10T09:00:00Z",
            summary: "Mock fixture · initial saved document",
          },
        ],
        commit: version,
        body: version ? body : null,
        diff: !version
          ? null
          : current === body
            ? ""
            : [
                `--- ${path}@${commit.slice(0, 8)}`,
                `+++ ${path} (working copy)`,
                `@@ -1,${before.length} +1,${after.length} @@`,
                ...before.map((line) => `-${line}`),
                ...after.map((line) => `+${line}`),
                "",
              ].join("\n"),
      });
    }),
  ];
}
