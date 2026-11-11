import { describe, expect, it } from "@rstest/core";
import { getResponse } from "msw";
import type { DocRelations, DocRelationUpdate } from "@/api/knowledge";
import { showcaseKnowledgeEdges } from "../knowledge-links";
import { createKnowledgeRelationHandlers } from "../knowledge-relations";

Reflect.set(globalThis, "location", new URL("http://localhost/"));

const source = "projects/p/knowledges/source.md";
const target = "projects/p/knowledges/target.md";
const fixture = () => {
  const notes = new Map([
    [
      source,
      {
        relPath: source,
        body: "See [result](target.md) here.\n```md\n[example](target.md)\n```\n",
        links: [] as string[],
      },
    ],
    [target, { relPath: target, body: "# Target\n", links: [] as string[] }],
  ]);
  const handlers = createKnowledgeRelationHandlers(notes, () => {});
  const url = `http://localhost/api/knowledge/doc/relations?path=${encodeURIComponent(source)}`;
  const get = async () =>
    (await (await getResponse(handlers, new Request(url)))?.json()) as DocRelations;
  const update = (payload: DocRelationUpdate) =>
    getResponse(
      handlers,
      new Request(url, {
        method: "PATCH",
        body: JSON.stringify(payload),
        headers: { "Content-Type": "application/json" },
      }),
    );
  return { notes, get, update };
};

describe("showcase relation authoring", () => {
  it("edits the original narrative and graph, preserves examples, and rejects stale writes", async () => {
    const { notes, get, update } = fixture();
    const original = await get();
    expect(original.relations).toHaveLength(1);
    const response = await update({
      action: "replace",
      id: 0,
      role: "supports",
      ifMatch: original.digest,
    });
    expect(response?.status).toBe(200);
    const changed = (await response?.json()) as DocRelations;
    expect(changed.digest).not.toBe(original.digest);
    expect(notes.get(source)?.body).toBe(
      "See [@supports result](target.md) here.\n```md\n[example](target.md)\n```\n",
    );
    expect(showcaseKnowledgeEdges(notes)).toEqual([
      { source, target, role: "supports", kind: "document" },
    ]);
    expect((await update({ action: "remove", id: 0, ifMatch: original.digest }))?.status).toBe(409);
    expect((await update({ action: "remove", id: 0, ifMatch: changed.digest }))?.status).toBe(200);
    expect(notes.get(source)?.body).toContain("See result here.");
    expect((await get()).relations).toHaveLength(0);
  });

  it("adds a relative typed link and serializes concurrent writes", async () => {
    const { notes, get, update } = fixture();
    const original = await get();
    const responses = await Promise.all([
      update({ action: "add", target, role: "cites", text: "Evidence", ifMatch: original.digest }),
      update({ action: "remove", id: 0, ifMatch: original.digest }),
    ]);
    expect(responses.map((response) => response?.status).sort()).toEqual([200, 409]);
    expect(notes.get(source)?.body).toContain("- [@cites Evidence](target.md)");
    const current = await get();
    const rejected = await update({
      action: "add",
      target: "../escape.md",
      role: "references",
      ifMatch: current.digest,
    });
    expect(rejected?.status).toBe(422);
  });
});
