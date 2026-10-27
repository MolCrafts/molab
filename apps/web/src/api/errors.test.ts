import { describe, expect, it } from "@rstest/core";
import { activeNeedsAuth, isSoftRemoteWait, shouldShowFailure } from "@/api/errors";
import { ApiError } from "@/api/generated/core/ApiError";

const unavailable = new ApiError(
  { method: "GET", url: "/api/workspace/scope" },
  {
    url: "/api/workspace/scope",
    ok: false,
    status: 503,
    statusText: "Service Unavailable",
    body: { error: { message: "needs_auth", details: { reason: "needs_auth" } } },
  },
  "Service Unavailable",
);

describe("quiet remote wait", () => {
  it("treats a verification-code 503 as a wait, not a failure to draw", () => {
    expect(isSoftRemoteWait(unavailable)).toBe(true);
    expect(isSoftRemoteWait(new Error("Request failed: 503 Service Unavailable"))).toBe(true);
    expect(isSoftRemoteWait("needs_auth")).toBe(true);
    expect(isSoftRemoteWait("unreachable")).toBe(true);
    expect(shouldShowFailure(unavailable, { needsAuth: true })).toBe(false);
    expect(shouldShowFailure(unavailable, { fetching: true })).toBe(false);
    expect(shouldShowFailure(unavailable)).toBe(false);
  });

  it("still draws a settled failure that is not the connect wait", () => {
    const failed = new Error("Request failed: 500 Internal Server Error");
    expect(isSoftRemoteWait(failed)).toBe(false);
    expect(shouldShowFailure(failed)).toBe(true);
    expect(shouldShowFailure(failed, { fetching: true })).toBe(false);
    expect(shouldShowFailure(null)).toBe(false);
  });

  it("reads the code wait from the active workspace", () => {
    expect(activeNeedsAuth([{ active: true, needsAuth: true }])).toBe(true);
    expect(activeNeedsAuth([{ active: false, needsAuth: true }, { active: true }])).toBe(false);
    expect(activeNeedsAuth([])).toBe(false);
  });
});
