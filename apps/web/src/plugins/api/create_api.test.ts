import { beforeEach, describe, expect, it } from "@rstest/core";
import { listFileTypeContributions, listRunViewContributions } from "@/lib/contribution-runtime";
import { createPluginAPI } from "@/plugins/api/create_api";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import { listCommands, listStatusBarItems } from "@/plugins/contributions/workbench";
import molplotPlugin from "@/plugins/molplot/plugin";
import molrsPlugin from "@/plugins/molrs/plugin";

beforeEach(() => {
  resetContributionRuntimeForTests();
});

function SampleFileType(): null {
  return null;
}

describe("createPluginAPI", () => {
  it("disposes contributions in LIFO order", () => {
    const order: string[] = [];
    const { api, disposeAll } = createPluginAPI("sample");
    api.commands.register("first", () => {
      order.push("first");
    });
    api.commands.register("second", () => {
      order.push("second");
    });
    expect(listCommands().map((command) => command.id)).toEqual([
      "plugin.sample.first",
      "plugin.sample.second",
    ]);
    disposeAll();
    expect(listCommands()).toEqual([]);
  });

  it("namespaces commands and status-bar items, keeps file-type ids", () => {
    const { api } = createPluginAPI("sample");
    api.commands.register("reload", () => {}, { title: "Reload" });
    api.statusBar.register({ id: "jobs", text: "0 jobs", command: "reload" });
    api.fileTypes.register({
      id: "sample:run-tab",
      objectType: "run",
      value: "sample",
      label: "Sample",
      matcher: { patterns: ["*.sample"] },
      Component: SampleFileType,
    });

    expect(listCommands()[0]?.id).toBe("plugin.sample.reload");
    expect(listStatusBarItems()[0]?.id).toBe("plugin.sample.jobs");
    expect(listStatusBarItems()[0]?.command).toBe("plugin.sample.reload");
    expect(listFileTypeContributions("run").map((item) => item.id)).toEqual(["sample:run-tab"]);
  });

  it("molplot registers its run view but claims no format by itself", () => {
    // molplot displays; it owns no format. With no reader contributed, the
    // view exists and matches nothing — which is the whole point of the seam.
    const { api } = createPluginAPI("molplot");
    void molplotPlugin.activate(api);
    const molplot = listRunViewContributions().find((item) => item.id === "molplot");
    expect(molplot).toBeDefined();
    expect(listFileTypeContributions("run").some((item) => item.pluginId === "molplot")).toBe(
      false,
    );
    expect(
      molplot?.files?.matches?.({
        name: "metrics.mlp.jsonl",
        relPath: "out/metrics.mlp.jsonl",
        type: "file",
      }),
    ).toBe(false);
  });

  it("a contributed reader is what makes a file plottable", () => {
    // molrs owns the formats and contributes the readers; composing the two
    // plugins is what lights up the view.
    const molrsApi = createPluginAPI("molrs");
    void molrsPlugin.activate(molrsApi.api);
    const { api } = createPluginAPI("molplot");
    void molplotPlugin.activate(api);

    const molplot = listRunViewContributions().find((item) => item.id === "molplot");
    expect(
      molplot?.files?.matches?.({
        name: "metrics.mlp.jsonl",
        relPath: "out/metrics.mlp.jsonl",
        type: "file",
      }),
    ).toBe(true);
  });
});
