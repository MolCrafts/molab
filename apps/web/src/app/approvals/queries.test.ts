import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient } from "@tanstack/react-query";
import { ApprovalsService } from "@/api/generated/services/ApprovalsService";
import { pendingApprovalsQueryOptions } from "@/app/approvals/queries";

describe("pending approvals query", () => {
  afterEach(() => {
    rs.restoreAllMocks();
  });

  it("deduplicates concurrent consumers and reuses fresh data", async () => {
    const response = { items: [], total: 0 };
    const listSpy = rs
      .spyOn(ApprovalsService, "listPendingApprovals")
      .mockResolvedValue(response as never);
    const client = new QueryClient();

    const [first, second] = await Promise.all([
      client.fetchQuery(pendingApprovalsQueryOptions),
      client.fetchQuery(pendingApprovalsQueryOptions),
    ]);
    const third = await client.fetchQuery(pendingApprovalsQueryOptions);

    expect(first).toEqual(response);
    expect(second).toEqual(response);
    expect(third).toEqual(response);
    expect(listSpy).toHaveBeenCalledTimes(1);
  });
});
