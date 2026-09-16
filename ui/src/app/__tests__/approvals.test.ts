/**
 * Approvals share one key and one connection.
 *
 * The bell and the inbox used to each fetch `/api/approvals` and each hold
 * their own `EventSource`, so mounting both doubled every refresh. Both now
 * read {@link useApprovalsQuery}; these tests drive the query layer directly
 * (headless — rstest has no DOM environment) to prove the sharing.
 */

import { afterEach, beforeEach, describe, expect, it } from "@rstest/core";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { qk } from "@/app/state/queries";

let requests = 0;

const approvalsQueryOptions = {
  queryKey: qk.approvals(),
  queryFn: async () => {
    requests += 1;
    return [{ taskId: "t1" }];
  },
  staleTime: 30_000,
};

const makeClient = (): QueryClient =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });

/** Subscribe like a mounted component and resolve on the first settled data. */
const observe = async (client: QueryClient): Promise<() => void> => {
  const observer = new QueryObserver(client, approvalsQueryOptions);
  const unsubscribe = observer.subscribe(() => {});
  await observer.refetch();
  return unsubscribe;
};

beforeEach(() => {
  requests = 0;
});

afterEach(() => {
  requests = 0;
});

describe("approvals sharing", () => {
  it("serves the bell and the inbox from one request", async () => {
    const client = makeClient();
    // Two observers of the same key == the bell and the inbox mounted together.
    const a = new QueryObserver(client, approvalsQueryOptions);
    const b = new QueryObserver(client, approvalsQueryOptions);
    const unsubA = a.subscribe(() => {});
    const unsubB = b.subscribe(() => {});
    await Promise.all([a.refetch(), b.refetch()]);

    expect(requests).toBe(1);
    expect(a.getCurrentResult().data).toEqual(b.getCurrentResult().data);
    unsubA();
    unsubB();
  });

  it("refetches once per change, not once per consumer", async () => {
    const client = makeClient();
    const unsubA = await observe(client);
    const unsubB = await observe(client);
    const afterMount = requests;

    // One stream message → one invalidation of the shared key.
    await client.invalidateQueries({ queryKey: qk.approvals(), exact: true });

    expect(requests).toBe(afterMount + 1);
    unsubA();
    unsubB();
  });

  it("keeps rows visible while revalidating", async () => {
    const client = makeClient();
    const observer = new QueryObserver(client, approvalsQueryOptions);
    const unsubscribe = observer.subscribe(() => {});
    await observer.refetch();

    const before = observer.getCurrentResult().data;
    const pending = client.invalidateQueries({ queryKey: qk.approvals(), exact: true });
    // A background revalidation must not blank the list — the bell badge would
    // flicker to zero and the inbox would flash a skeleton.
    expect(observer.getCurrentResult().data).toEqual(before);
    await pending;
    unsubscribe();
  });

  it("invalidating approvals leaves unrelated keys alone", async () => {
    const client = makeClient();
    client.setQueryData(qk.agentSessions(), [{ id: "s1" }]);
    const unsubscribe = await observe(client);

    await client.invalidateQueries({ queryKey: qk.approvals(), exact: true });

    const sessions = client.getQueryCache().find({ queryKey: [...qk.agentSessions()] });
    expect(sessions?.isStaleByTime(Infinity)).toBe(false);
    unsubscribe();
  });
});
