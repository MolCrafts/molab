import { afterEach, describe, expect, it, rstest } from "@rstest/core";
import { ApiError } from "@/api/generated/core/ApiError";
import { workspaceApi } from "./workspace";

const previousFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = previousFetch;
});

describe("workspace uploads", () => {
  it("sends the file body once and preserves uncertain outcomes", async () => {
    const fetch = rstest.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: "OUTCOME_UNKNOWN", outcome: "unknown", message: "Transfer interrupted" },
        }),
        { status: 409 },
      ),
    );
    globalThis.fetch = fetch;
    try {
      await workspaceApi.uploadFile("data.bin", new File(["data"], "data.bin"), "workspace");
      expect.unreachable("upload reported success");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).body.error.outcome).toBe("unknown");
      expect((error as Error).message).toContain("Check the destination");
    }
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[1].body).toBeInstanceOf(File);
  });

  it("does not resend after a lost HTTP connection", async () => {
    const fetch = rstest.fn().mockRejectedValue(new TypeError("connection lost"));
    globalThis.fetch = fetch;
    await expect(workspaceApi.uploadFile("file", new File(["data"], "file"))).rejects.toThrow(
      "could not be confirmed",
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
