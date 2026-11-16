import { afterEach, describe, expect, it } from "@rstest/core";
import {
  dismissRemoteAuth,
  noteRemoteAuthResponse,
  noteRemoteAuthState,
  parseNeedsAuthKey,
  requestRemoteAuth,
  resetRemoteAuthForTests,
  setRemoteAuthFallback,
  subscribeRemoteAuth,
} from "@/app/layout/remoteAuthPrompt";
import type { ServedWorkspaceSummary } from "@/app/types";

const remote = (patch: Partial<ServedWorkspaceSummary> = {}): ServedWorkspaceSummary => ({
  key: "arrhenius",
  label: "Arrhenius:/home/lab",
  isRemote: true,
  path: null,
  active: true,
  unreachable: true,
  needsAuth: true,
  ...patch,
});

afterEach(() => {
  resetRemoteAuthForTests();
});

describe("remote auth prompt", () => {
  it("opens when a remote workspace needs a verification code", () => {
    const seen: string[] = [];
    subscribeRemoteAuth((workspace) => seen.push(workspace.key));
    noteRemoteAuthState(remote());
    expect(seen).toEqual(["arrhenius"]);
  });

  it("does not mistake an unreachable host for an authentication request", () => {
    const seen: string[] = [];
    subscribeRemoteAuth((workspace) => seen.push(workspace.key));
    noteRemoteAuthState(remote({ needsAuth: false, unreachable: true }));
    expect(seen).toEqual([]);
    dismissRemoteAuth("arrhenius");
    noteRemoteAuthState(remote({ needsAuth: false, unreachable: true }));
    noteRemoteAuthState(remote());
    expect(seen).toEqual([]);
  });

  it("stays quiet after Esc until the host is healthy again", () => {
    const seen: string[] = [];
    subscribeRemoteAuth((workspace) => seen.push(workspace.key));
    noteRemoteAuthState(remote());
    dismissRemoteAuth("arrhenius");
    noteRemoteAuthState(remote());
    expect(seen).toEqual(["arrhenius"]);

    noteRemoteAuthState(remote({ needsAuth: false, unreachable: false }));
    noteRemoteAuthState(remote());
    expect(seen).toEqual(["arrhenius", "arrhenius"]);
  });

  it("reopens on an explicit reconnect after Esc", () => {
    const seen: string[] = [];
    subscribeRemoteAuth((workspace) => seen.push(workspace.label));
    dismissRemoteAuth("arrhenius");
    requestRemoteAuth(remote(), "gesture");
    expect(seen).toEqual(["Arrhenius:/home/lab"]);
  });

  it("reads needs_auth from the API error envelope", () => {
    expect(
      parseNeedsAuthKey({
        error: {
          code: "REMOTE_WORKSPACE_UNREACHABLE",
          message: "needs_auth",
          details: { reason: "needs_auth", workspace: "arrhenius" },
        },
      }),
    ).toBe("arrhenius");
    expect(
      parseNeedsAuthKey({ error: { message: "unreachable", details: { reason: "unreachable" } } }),
    ).toBe(null);
  });

  it("opens from a 503 needs_auth response, using the active remote when the body has no key", async () => {
    const seen: string[] = [];
    subscribeRemoteAuth((workspace) => seen.push(workspace.key));
    setRemoteAuthFallback(remote({ key: "active-host", needsAuth: false, unreachable: false }));
    await noteRemoteAuthResponse(
      new Response(
        JSON.stringify({ error: { message: "needs_auth", details: { reason: "needs_auth" } } }),
        {
          status: 503,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    expect(seen).toEqual(["active-host"]);
  });

  it("ignores a 503 that is not a verification-code request", async () => {
    const seen: string[] = [];
    subscribeRemoteAuth(() => seen.push("opened"));
    await noteRemoteAuthResponse(
      new Response(JSON.stringify({ error: { message: "unreachable" } }), { status: 503 }),
    );
    expect(seen).toEqual([]);
  });
});
