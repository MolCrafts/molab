import { beforeEach, describe, expect, it, rs } from "@rstest/core";
import { listPluginCatalog, resetPluginCatalogForTests } from "@/plugins/catalog";
import {
  createLoaderState,
  loadInternalPlugin,
  registerInternalPluginDescriptors,
} from "@/plugins/loader";
import type { InternalPluginDescriptor } from "@/plugins/types";

const descriptor = (
  id: string,
  load: InternalPluginDescriptor["load"],
): InternalPluginDescriptor => ({
  id,
  name: id.toUpperCase(),
  description: `${id} capability`,
  userToggleable: true,
  load,
});

describe("internal plugin descriptors", () => {
  beforeEach(() => resetPluginCatalogForTests());

  it("registers lightweight catalog metadata without loading implementations", () => {
    const load = rs.fn();

    registerInternalPluginDescriptors([descriptor("alpha", load as never)]);

    expect(load).not.toHaveBeenCalled();
    expect(listPluginCatalog()).toEqual([
      {
        id: "alpha",
        name: "ALPHA",
        description: "alpha capability",
        userToggleable: true,
      },
    ]);
  });

  it("deduplicates concurrent loads and registers the matching module once", async () => {
    const register = rs.fn();
    const load = rs.fn().mockResolvedValue({
      default: { id: "alpha", register },
    });
    const state = createLoaderState();
    const item = descriptor("alpha", load as never);

    await Promise.all([loadInternalPlugin(state, item), loadInternalPlugin(state, item)]);

    expect(load).toHaveBeenCalledTimes(1);
    expect(register).toHaveBeenCalledTimes(1);
    expect(state.installed.has("alpha")).toBe(true);
  });

  it("isolates a module whose exported id does not match its descriptor", async () => {
    const warn = rs.spyOn(console, "warn").mockImplementation(() => {});
    const state = createLoaderState();
    const item = descriptor(
      "alpha",
      rs.fn().mockResolvedValue({
        default: { id: "different", register: rs.fn() },
      }) as never,
    );

    await expect(loadInternalPlugin(state, item)).resolves.not.toThrow();

    expect(state.installed.has("alpha")).toBe(false);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
