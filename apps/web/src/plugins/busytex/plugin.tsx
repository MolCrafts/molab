import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";

const TexPreview = lazyWithPrefetch(() =>
  import("./TexPreview").then((module) => ({ default: module.TexPreview })),
);

const busytexPlugin: MolabPluginModule = {
  id: "busytex",
  name: "BusyTeX",
  version: "1.0.0",
  description: "Compiles .tex files to PDF in the browser with TeXlyre BusyTeX pdfLaTeX.",
  activate: (api: PluginAPI) => {
    api.filePreviews.register({
      id: "busytex:preview",
      name: "BusyTeX",
      extensions: [".tex", ".ltx"],
      priority: 20,
      Component: TexPreview,
    });
  },
};

export default busytexPlugin;
