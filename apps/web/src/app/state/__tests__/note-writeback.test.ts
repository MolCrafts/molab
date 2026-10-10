import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { knowledgeApi } from "@/api";
import { KnowledgeService } from "@/api/generated/services/KnowledgeService";

const PUT = "editDoc" as const;

describe("knowledgeApi.editDoc", () => {
  afterEach(() => {
    rs.restoreAllMocks();
  });

  it("persists through the generated KnowledgeService, not a hand-rolled fetch", async () => {
    const detail = {
      body: "hello",
      cards: [],
      links: [],
      name: "Intro",
      relPath: "notes/intro",
    };
    const putSpy = rs.spyOn(KnowledgeService, PUT).mockResolvedValue(detail as never);
    const fetchSpy = rs.spyOn(globalThis, "fetch");

    const result = await knowledgeApi.editDoc("notes/intro", "hello");

    expect(putSpy).toHaveBeenCalledWith("notes/intro", { body: "hello" });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result).toEqual(detail);
  });
});
