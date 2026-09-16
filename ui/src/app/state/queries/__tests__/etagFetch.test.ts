/**
 * Conditional fetch contract: the ETag is remembered per URL, sent back only
 * when cached data exists, a 304 yields the *same* reference (so structural
 * sharing and `useMemo` short-circuit), and an unexpected 304 is retried once.
 */

import { afterAll, afterEach, beforeAll, describe, expect, it } from "@rstest/core";
import { HttpResponse, http } from "msw";
import {
  fetchJsonConditional,
  getStoredEtag,
  HttpStatusError,
  resetEtagCache,
} from "@/app/state/queries/etagFetch";
import { makeMswServer } from "@/test/queryTestUtils";

const URL = "http://localhost/api/etag-probe";
const harness = makeMswServer();

beforeAll(() => harness.server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  harness.reset();
  resetEtagCache();
});
afterAll(() => harness.server.close());

/** A handler that answers 304 to a matching If-None-Match, else 200 + ETag. */
const versioned = (etag: string, body: Record<string, unknown>) =>
  http.get(URL, ({ request }) => {
    if (request.headers.get("if-none-match") === etag) {
      return new HttpResponse(null, { status: 304, headers: { ETag: etag } });
    }
    return HttpResponse.json(body, { headers: { ETag: etag } });
  });

describe("fetchJsonConditional", () => {
  it("returns the body and remembers the ETag; first call is unconditional", async () => {
    harness.server.use(versioned('"v1"', { v: 1 }));
    const data = await fetchJsonConditional<{ v: number }>(URL);
    expect(data).toEqual({ v: 1 });
    expect(getStoredEtag(URL)).toBe('"v1"');
    expect(harness.requestsTo("etag-probe")[0]?.headers["if-none-match"]).toBeUndefined();
  });

  it("sends If-None-Match when previous data exists and hands it back on 304", async () => {
    harness.server.use(versioned('"v1"', { v: 1 }));
    const first = await fetchJsonConditional<{ v: number }>(URL);
    const second = await fetchJsonConditional<{ v: number }>(URL, { previous: () => first });
    expect(second).toBe(first);
    const requests = harness.requestsTo("etag-probe");
    expect(requests).toHaveLength(2);
    expect(requests[1]?.headers["if-none-match"]).toBe('"v1"');
  });

  it("omits the header (and refetches) when the cached data was evicted", async () => {
    harness.server.use(versioned('"v1"', { v: 1 }));
    await fetchJsonConditional(URL);
    const again = await fetchJsonConditional<{ v: number }>(URL, { previous: () => undefined });
    expect(again).toEqual({ v: 1 });
    expect(harness.requestsTo("etag-probe")[1]?.headers["if-none-match"]).toBeUndefined();
  });

  it("retries once without the header on an unexpected 304", async () => {
    let calls = 0;
    harness.server.use(
      http.get(URL, () => {
        calls += 1;
        return calls === 1
          ? new HttpResponse(null, { status: 304 })
          : HttpResponse.json({ v: 2 }, { headers: { ETag: '"v2"' } });
      }),
    );
    const data = await fetchJsonConditional<{ v: number }>(URL, { previous: () => undefined });
    expect(data).toEqual({ v: 2 });
    expect(calls).toBe(2);
    expect(getStoredEtag(URL)).toBe('"v2"');
  });

  it("throws HttpStatusError carrying the status on a non-2xx", async () => {
    harness.server.use(http.get(URL, () => HttpResponse.json({ detail: "down" }, { status: 503 })));
    const failure = await fetchJsonConditional(URL).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(HttpStatusError);
    expect((failure as HttpStatusError).status).toBe(503);
    expect((failure as HttpStatusError).body).toEqual({ detail: "down" });
  });

  it("forgets a URL's ETag when a fresh 200 comes back without one", async () => {
    harness.server.use(versioned('"v1"', { v: 1 }));
    await fetchJsonConditional(URL);
    harness.server.use(http.get(URL, () => HttpResponse.json({ v: 3 })));
    await fetchJsonConditional(URL, { previous: () => undefined });
    expect(getStoredEtag(URL)).toBeUndefined();
  });
});
