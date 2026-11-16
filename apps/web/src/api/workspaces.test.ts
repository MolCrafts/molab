import { afterEach, describe, expect, it, rstest } from "@rstest/core";
import { workspacesApi } from "./workspaces";

const previousFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = previousFetch;
});

describe("workspace authentication", () => {
  it("preserves the connection stage and backend diagnostic", async () => {
    const detail = "Connected, but cannot read this root: Unsupported entity metadata";
    globalThis.fetch = rstest
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 502 }));
    await expect(workspacesApi.connectWorkspace("remote", "fixture")).rejects.toThrow(detail);
  });

  it("preserves an invalid workspace response instead of showing failed", async () => {
    const detail = "Unknown workspace: remote-descriptor";
    globalThis.fetch = rstest
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 404 }));
    await expect(workspacesApi.connectWorkspace("remote", "fixture")).rejects.toThrow(detail);
  });
});

it("publishes the replacement connection when the active root is removed", async () => {
  const { onWorkspaceSwitching } = await import("@/app/state/workspaceSwitchEvents");
  const oldWindow = globalThis.window;
  rstest.stubGlobal("window", new EventTarget());
  const switched: (string | null)[] = [];
  const stop = onWorkspaceSwitching((detail) => switched.push(detail.activeDescriptor));
  globalThis.fetch = rstest
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify([{ key: "remaining", label: "Remaining", active: true, isRemote: false }]),
        { headers: { "Content-Type": "application/json" } },
      ),
    );
  try {
    await workspacesApi.removeWorkspace("deleted");
    expect(switched).toEqual(["remaining"]);
  } finally {
    stop();
    rstest.stubGlobal("window", oldWindow);
  }
});
