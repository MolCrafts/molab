import { type JSX, useMemo } from "react";
import { LazySurface } from "@/app/layout/LazySurface";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";

/**
 * Open a TeX file with whichever preview plugin claimed `.tex`.
 * The knowledge plugin does not import that engine. With no preview
 * registered, the source is the view.
 */
export const TexDocumentView = ({
  content,
  name,
  path,
}: {
  content: string;
  name: string;
  path: string;
}): JSX.Element => {
  const generation = useContributionGeneration();
  const plugin = useMemo(() => {
    void generation;
    return filePreviewPluginRegistry.getPluginForFile(name, path);
  }, [generation, name, path]);

  if (!plugin) {
    return (
      <pre className="h-full overflow-auto px-4 py-6 font-mono text-label text-foreground md:px-8">
        {content}
      </pre>
    );
  }

  const Preview = plugin.Component;
  return (
    <LazySurface
      resetKey={`knowledge-tex:${plugin.id}:${path}`}
      loadingTitle={`Loading ${plugin.name}…`}
      className="h-full"
    >
      <Preview content={content} name={name} path={path} folderId="knowledge" />
    </LazySurface>
  );
};
