import { describe, expect, it } from "@rstest/core";
import { presentWorkspaceLoad } from "@/app/state/useWorkspaceState";

const query = (
  overrides: Partial<{
    isError: boolean;
    isPending: boolean;
    isFetching: boolean;
    error: unknown;
  }> = {},
) => ({
  isError: false,
  isPending: false,
  isFetching: false,
  error: null,
  ...overrides,
});

describe("presentWorkspaceLoad", () => {
  it("stays quiet while a request is in flight, even if an earlier attempt failed", () => {
    const presented = presentWorkspaceLoad(
      [query({ isError: true, isFetching: true, error: new Error("Request failed: 503") })],
      false,
    );
    expect(presented).toEqual({ status: "loading", error: null });
  });

  it("does not fail the page while the verification code is still open", () => {
    const presented = presentWorkspaceLoad(
      [query({ isError: true, error: new Error("Request failed: 503 Service Unavailable") })],
      true,
    );
    expect(presented).toEqual({ status: "ready", error: null });
  });

  it("keeps a settled host-down 503 off the error page", () => {
    const presented = presentWorkspaceLoad(
      [query({ isError: true, error: new Error("Service Unavailable") })],
      false,
    );
    expect(presented).toEqual({ status: "ready", error: null });
  });

  it("shows a settled failure once loading and the code prompt are done", () => {
    const error = new Error("Request failed: 500 Internal Server Error");
    const presented = presentWorkspaceLoad([query({ isError: true, error })], false);
    expect(presented.status).toBe("error");
    expect(presented.error).toBe(error);
  });
});
