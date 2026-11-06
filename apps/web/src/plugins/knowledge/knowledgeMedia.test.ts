import { describe, expect, it } from "@rstest/core";
import {
  knowledgeBlobUrl,
  posixRelative,
  proxyKnowledgeImageUrl,
  resolveKnowledgeMediaPath,
  restoreKnowledgeMedia,
  rewriteKnowledgeMedia,
} from "./knowledgeMedia";

const DOC = "projects/nve-shifting/knowledges/fp32-drift-is-unwrapped-coordinates.md";

describe("resolveKnowledgeMediaPath", () => {
  it("resolves a sibling figs/ path against the document", () => {
    expect(resolveKnowledgeMediaPath(DOC, "figs/figA_mechanism.png")).toBe(
      "projects/nve-shifting/knowledges/figs/figA_mechanism.png",
    );
  });

  it("leaves http, data, and /api/ sources alone", () => {
    expect(resolveKnowledgeMediaPath(DOC, "https://example.com/a.png")).toBeNull();
    expect(resolveKnowledgeMediaPath(DOC, "data:image/png;base64,xx")).toBeNull();
    expect(resolveKnowledgeMediaPath(DOC, "/api/workspace/file/blob?path=x")).toBeNull();
  });
});

describe("rewriteKnowledgeMedia / restoreKnowledgeMedia", () => {
  it("round-trips a relative image back to the same markdown", () => {
    const body = "see\n\n![刚体平移](figs/figA_mechanism.png)\n";
    const display = rewriteKnowledgeMedia(body, DOC);
    const blob = knowledgeBlobUrl("projects/nve-shifting/knowledges/figs/figA_mechanism.png");
    expect(display).toContain(`(<${blob}>)`);
    expect(restoreKnowledgeMedia(display, DOC)).toBe(body);
  });

  it("does not rewrite a PDF markdown link (not an image)", () => {
    const body = "[figA PDF](figs/figA_mechanism.pdf)";
    expect(rewriteKnowledgeMedia(body, DOC)).toBe(body);
  });

  it("does not rewrite an already-absolute image", () => {
    const body = "![x](https://cdn.example/a.png)";
    expect(rewriteKnowledgeMedia(body, DOC)).toBe(body);
  });
});

describe("proxyKnowledgeImageUrl", () => {
  it("maps a relative figure onto the workspace blob route", () => {
    expect(proxyKnowledgeImageUrl(DOC, "figs/figA_mechanism.png")).toBe(
      knowledgeBlobUrl("projects/nve-shifting/knowledges/figs/figA_mechanism.png"),
    );
  });
});

describe("posixRelative", () => {
  it("drops the shared prefix down to figs/file", () => {
    expect(
      posixRelative(
        "projects/nve-shifting/knowledges",
        "projects/nve-shifting/knowledges/figs/figA_mechanism.png",
      ),
    ).toBe("figs/figA_mechanism.png");
  });
});
