import type {
  CommandRegisterOptions,
  Disposer,
  EditorContribution,
  EntityTabContribution,
  ExecutionColumnContribution,
  ExecutionDetailContribution,
  FilePreviewContribution,
  FileTypeContribution,
  InspectorContribution,
  PluginAPI,
  PluginCommandFn,
  PluginLogger,
  PluginPanelSpec,
  SettingsSectionSpec,
  StatusBarItemSpec,
  ViewContainerSpec,
  ViewSpec,
} from "@molcrafts/molab-plugin";
import { namespacePluginId } from "@molcrafts/molab-plugin";
import type { RendererKey } from "@/app/types";
import {
  registerEntityTabContribution,
  registerExecutionColumnContribution,
  registerExecutionDetailContribution,
  registerFilePreviewContribution,
  registerFileTypeContribution,
  registerRendererContribution,
  unregisterEntityTabContribution,
  unregisterExecutionColumnContribution,
  unregisterExecutionDetailContribution,
  unregisterFilePreviewContribution,
  unregisterFileTypeContribution,
  unregisterRendererContribution,
} from "@/lib/contribution-runtime";
import type {
  FilePreviewPlugin,
  EntityTabContribution as HostEntityTab,
  ExecutionColumnContribution as HostExecutionColumn,
  ExecutionDetailContribution as HostExecutionDetail,
  FileTypeContribution as HostFileType,
  RendererContribution,
} from "@/lib/contribution-types";
import {
  registerCommand,
  registerPanel,
  registerSettingsSection,
  registerStatusBarItem,
  registerView,
  registerViewContainer,
} from "@/plugins/contributions/workbench";
import { pluginStorageNamespace } from "@/plugins/storage";

export interface CreatedPluginAPI {
  api: PluginAPI;
  disposeAll: () => void;
}

function makeLogger(pluginId: string): PluginLogger {
  const tag = `[plugin:${pluginId}]`;
  return {
    info: (...args) => console.info(tag, ...args),
    warn: (...args) => console.warn(tag, ...args),
    error: (...args) => console.error(tag, ...args),
  };
}

function ns(pluginId: string, id: string): string {
  return namespacePluginId(pluginId, id);
}

function asRendererKey(key: EditorContribution["key"]): RendererKey {
  return key as RendererKey;
}

function toRendererContribution(
  spec: EditorContribution,
  pluginId: string,
  panelSlot: "center" | "right",
): RendererContribution {
  return {
    id: spec.id,
    key: asRendererKey(spec.key),
    title: spec.title,
    panelSlot,
    pluginId: spec.pluginId ?? pluginId,
    priority: spec.priority,
    matches: spec.matches as RendererContribution["matches"],
    Component: spec.Component as RendererContribution["Component"],
  };
}

export function createPluginAPI(pluginId: string): CreatedPluginAPI {
  const disposers: Disposer[] = [];
  const track = (d: Disposer): void => {
    disposers.push(d);
  };

  const api: PluginAPI = {
    pluginId,
    log: makeLogger(pluginId),
    storage: pluginStorageNamespace(pluginId),

    commands: {
      register<A, R>(id: string, fn: PluginCommandFn<A, R>, options?: CommandRegisterOptions) {
        const namespaced = ns(pluginId, id);
        track(
          registerCommand({
            id: namespaced,
            pluginId,
            title: options?.title ?? id,
            category: options?.category,
            keybinding: options?.keybinding,
            isVisible: options?.isVisible,
            run: (args) => fn(args as A),
          }),
        );
      },
    },

    views: {
      registerContainer(spec: ViewContainerSpec) {
        track(
          registerViewContainer({
            ...spec,
            pluginId,
          }),
        );
      },
      register(spec: ViewSpec) {
        track(
          registerView({
            ...spec,
            pluginId,
          }),
        );
      },
    },

    editors: {
      register(spec: EditorContribution) {
        const contribution = toRendererContribution(spec, pluginId, spec.panelSlot ?? "center");
        registerRendererContribution(contribution);
        track(() => {
          unregisterRendererContribution(contribution.id);
        });
      },
    },

    inspectors: {
      register(spec: InspectorContribution) {
        const contribution = toRendererContribution(spec, pluginId, spec.panelSlot ?? "right");
        registerRendererContribution(contribution);
        track(() => {
          unregisterRendererContribution(contribution.id);
        });
      },
    },

    panels: {
      register(spec: PluginPanelSpec) {
        if (spec.position !== "bottom") {
          throw new Error(
            `Plugin panel position '${String(spec.position)}' is not supported (v1: bottom only)`,
          );
        }
        const id = ns(pluginId, spec.id);
        track(registerPanel({ ...spec, id, pluginId }));
      },
    },

    statusBar: {
      register(spec: StatusBarItemSpec) {
        const id = ns(pluginId, spec.id);
        const command = spec.command
          ? spec.command.startsWith("plugin.")
            ? spec.command
            : ns(pluginId, spec.command)
          : undefined;
        track(registerStatusBarItem({ ...spec, id, command, pluginId }));
      },
    },

    settings: {
      registerSection(spec: SettingsSectionSpec) {
        const id = ns(pluginId, spec.id);
        track(registerSettingsSection({ ...spec, id, pluginId }));
      },
    },

    fileTypes: {
      register(spec: FileTypeContribution) {
        const stamped = {
          ...spec,
          pluginId: spec.pluginId ?? pluginId,
        } as HostFileType;
        registerFileTypeContribution(stamped);
        track(() => {
          unregisterFileTypeContribution(stamped.id);
        });
      },
    },

    entityTabs: {
      register(spec: EntityTabContribution) {
        const stamped = {
          ...spec,
          pluginId: spec.pluginId ?? pluginId,
        } as HostEntityTab;
        registerEntityTabContribution(stamped);
        track(() => {
          unregisterEntityTabContribution(stamped.id);
        });
      },
    },

    execution: {
      registerColumn(spec: ExecutionColumnContribution) {
        const stamped = {
          ...spec,
          pluginId: spec.pluginId ?? pluginId,
        } as HostExecutionColumn;
        registerExecutionColumnContribution(stamped);
        track(() => {
          unregisterExecutionColumnContribution(stamped.id);
        });
      },
      registerDetail(spec: ExecutionDetailContribution) {
        const stamped = {
          ...spec,
          pluginId: spec.pluginId ?? pluginId,
        } as HostExecutionDetail;
        registerExecutionDetailContribution(stamped);
        track(() => {
          unregisterExecutionDetailContribution(stamped.id);
        });
      },
    },

    filePreviews: {
      register(spec: FilePreviewContribution) {
        const stamped = {
          ...spec,
          pluginId: spec.pluginId ?? pluginId,
        } as FilePreviewPlugin;
        registerFilePreviewContribution(stamped);
        track(() => {
          unregisterFilePreviewContribution(stamped.id);
        });
      },
    },
  };

  return {
    api,
    disposeAll: () => {
      for (let i = disposers.length - 1; i >= 0; i -= 1) {
        try {
          disposers[i]();
        } catch (err) {
          console.error(`[plugin:${pluginId}] dispose failed`, err);
        }
      }
      disposers.length = 0;
    },
  };
}
