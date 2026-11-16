import { afterEach, describe, expect, it, rstest } from "@rstest/core";
import { sharingApi } from "./sharing";

afterEach(() => {
  rstest.restoreAllMocks();
});

describe("sharing transport boundary", () => {
  it("uses the sharing API, encodes resource IDs, and propagates cancellation", async () => {
    const fetch = rstest.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    const controller = new AbortController();
    await sharingApi.project("a/b?ws=private", controller.signal);
    expect(fetch).toHaveBeenCalledWith(
      "/api/sharing/projects/a%2Fb%3Fws%3Dprivate",
      expect.objectContaining({
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      }),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not fall back to private workspace APIs when a grant is revoked", async () => {
    const fetch = rstest
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("private diagnostics", { status: 404 }));
    await expect(sharingApi.project("revoked")).rejects.toThrow(
      "This share is no longer available.",
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("binds invitations to a recipient without browser source credentials", async () => {
    const fetch = rstest.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    await sharingApi.invite("p", "bob-id");
    expect(fetch).toHaveBeenCalledWith(
      "/api/sharing/projects/p/invitations",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipient_id: "bob-id", role: "viewer" }),
      }),
    );
  });

  it("requires a new review after a conflicting publication", async () => {
    rstest.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 409 }));
    await expect(sharingApi.publish({ project_id: "p" }, "old-review")).rejects.toThrow(
      "Refresh the preview",
    );
  });

  it("explains publication limits without echoing arbitrary validation inputs", async () => {
    rstest
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "A selected metric exceeds the 2000-point publication limit" }),
          { status: 422 },
        ),
      );
    await expect(sharingApi.preview({ project_id: "p" })).rejects.toThrow(
      "2000-point publication limit",
    );
  });
});
