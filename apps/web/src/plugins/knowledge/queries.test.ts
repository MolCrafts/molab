import { beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient } from "@tanstack/react-query";
import { knowledgeApi } from "@/api";
import { knowledgeListQueryOptions } from "./queries";

rs.mock("@/api", () => ({
  knowledgeApi: {
    listKnowledge: rs.fn(),
  },
}));

describe("knowledge queries", () => {
  beforeEach(() => {
    rs.clearAllMocks();
  });

  it("deduplicates concurrent inventory consumers through the shared query key", async () => {
    rs.mocked(knowledgeApi.listKnowledge).mockResolvedValue({
      notes: [],
      references: [],
      total: 0,
    });
    const client = new QueryClient();
    const options = knowledgeListQueryOptions();

    await Promise.all([client.fetchQuery(options), client.fetchQuery(options)]);

    expect(knowledgeApi.listKnowledge).toHaveBeenCalledTimes(1);
  });

  it("keeps filtered and unfiltered inventories in separate cache entries", () => {
    expect(knowledgeListQueryOptions().queryKey).not.toEqual(
      knowledgeListQueryOptions({ tag: "simulation" }).queryKey,
    );
  });
});
