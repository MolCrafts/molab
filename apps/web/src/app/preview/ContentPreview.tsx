/**
 * Asset, file and knowledge-document Previews (Figma L12-5 … L12-7): what it
 * is, where it came from, the first lines of it. A file or a document is a
 * definition, so neither carries a status.
 */

import { useQuery } from "@tanstack/react-query";
import type { JSX } from "react";
import { assetsApi } from "@/api/assets";
import { entityMeta } from "@/app/entities/kinds";
import { runLabel } from "@/app/runs/runTitle";
import { getWorkspaceQueryScope } from "@/app/state/workspaceSwitchEvents";
import type { WorkspaceSnapshot } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import { formatBytes } from "@/lib/format-bytes";
import { getWorkspaceFs } from "@/lib/workspace-fs";
import { useKnowledgeBacklinksQuery, useKnowledgeNoteQuery } from "@/plugins/knowledge/queries";
import { KindIcon, PreviewFrame, PreviewKV, PreviewLink, PreviewSubhead } from "./PreviewFrame";
import { PreviewError, PreviewGone, PreviewLoading } from "./PreviewStates";
import { PreviewRow } from "./previewParts";
import type { PreviewTarget } from "./target";

type ContentTarget = Extract<PreviewTarget, { kind: "asset" | "file" | "knowledge" }>;

interface ContentPreviewProps {
  target: ContentTarget;
  snapshot: WorkspaceSnapshot;
  onPreview: (target: PreviewTarget) => void;
  onOpen: (target: PreviewTarget) => void;
  onOpenInBackground: () => void;
  onClose: () => void;
}

const HEAD_LINES = 11;
const lastSegment = (path: string): string => path.split("/").filter(Boolean).pop() ?? path;

const Head = ({ text, total }: { text: string; total?: number }): JSX.Element => {
  const lines = text.split("\n");
  return (
    <>
      <pre className="overflow-hidden rounded-hairline bg-muted px-2 py-2 font-mono text-micro leading-relaxed">
        {lines.slice(0, HEAD_LINES).map((line, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: a file's lines are positional
          <div key={index} className="flex gap-3">
            <span className="w-6 flex-none text-right text-muted-foreground">{index + 1}</span>
            <span className="whitespace-pre">{line}</span>
          </div>
        ))}
      </pre>
      {lines.length > HEAD_LINES ? (
        <p className="pl-6 text-label text-muted-foreground">
          first {HEAD_LINES} of {total ?? lines.length} lines
        </p>
      ) : null}
    </>
  );
};

const FilePreview = ({
  target,
  ...frame
}: Omit<ContentPreviewProps, "snapshot" | "onPreview"> & {
  target: Extract<PreviewTarget, { kind: "file" }>;
}): JSX.Element => {
  const text = useQuery({
    queryKey: ["preview-file-head", getWorkspaceQueryScope(), target.filePath],
    queryFn: () => getWorkspaceFs().readText(target.filePath),
    enabled: target.fileKind !== "image",
    staleTime: 30_000,
  });
  const props = {
    title: lastSegment(target.filePath),
    mono: true,
    onOpen: () => frame.onOpen(target),
    onOpenInBackground: frame.onOpenInBackground,
    onClose: frame.onClose,
  };
  if (text.isPending && target.fileKind !== "image")
    return <PreviewLoading {...props} kindLabel="file" />;
  if (text.isError) {
    // A file too large to read whole is not a failure: open it to page through it.
    if (text.error.message.includes("413")) {
      return (
        <PreviewFrame
          {...props}
          lead={<KindIcon icon={entityMeta("workspace-file").icon} />}
          context={`file · ${target.fileKind}`}
          copies={[{ label: "Path", value: target.filePath }]}
        >
          <p className="text-label text-muted-foreground">
            Too large to preview — open it to read.
          </p>
        </PreviewFrame>
      );
    }
    return (
      <PreviewError
        {...props}
        kindLabel="file"
        message={text.error.message}
        onRetry={() => void text.refetch()}
      />
    );
  }
  return (
    <PreviewFrame
      {...props}
      lead={<KindIcon icon={entityMeta("workspace-file").icon} />}
      context={`file · ${target.filePath.split("/").slice(0, -1).join("/") || "/"} · ${target.fileKind}`}
      copies={[{ label: "Path", value: target.filePath }]}
    >
      {target.fileKind === "image" ? (
        <p className="text-label text-muted-foreground">Image — open it to view.</p>
      ) : (
        <Head text={text.data ?? ""} />
      )}
    </PreviewFrame>
  );
};

const DocumentPreview = ({
  target,
  onPreview,
  ...frame
}: Omit<ContentPreviewProps, "snapshot"> & {
  target: Extract<PreviewTarget, { kind: "knowledge" }>;
}): JSX.Element => {
  const note = useKnowledgeNoteQuery(target.path);
  const backlinks = useKnowledgeBacklinksQuery(target.path);
  const title = note.data?.name ?? lastSegment(target.path);
  const props = {
    title,
    onOpen: () => frame.onOpen(target),
    onOpenInBackground: frame.onOpenInBackground,
    onClose: frame.onClose,
  };
  if (note.isPending) return <PreviewLoading {...props} kindLabel="document" />;
  if (note.isError) {
    return (
      <PreviewError
        {...props}
        kindLabel="document"
        message={note.error.message}
        onRetry={() => void note.refetch()}
      />
    );
  }
  const record = note.data.record ?? {};
  const cls = typeof record.class === "string" ? record.class : "Document";
  const firstParagraph =
    note.data.body
      .split(/\n\s*\n/)
      .map((part) => part.trim())
      .find((part) => part && !part.startsWith("#")) ?? "";
  const cited = backlinks.data?.backlinks ?? [];
  return (
    <PreviewFrame
      {...props}
      lead={<KindIcon icon={entityMeta("knowledge").icon} />}
      context={`${cls} · ${target.path.split("/knowledges/")[0] || "workspace"}`}
      copies={[{ label: "Path", value: target.path }]}
    >
      {firstParagraph ? (
        <p className="line-clamp-5 text-body leading-relaxed">{firstParagraph}</p>
      ) : null}
      {note.data.links.length > 0 ? (
        <>
          <PreviewSubhead>Cites</PreviewSubhead>
          <ul className="pl-6 text-body">
            {note.data.links.slice(0, 5).map((link) => (
              <PreviewRow key={link}>
                <span className="font-mono text-label">{link}</span>
              </PreviewRow>
            ))}
          </ul>
        </>
      ) : null}
      {cited.length > 0 ? (
        <>
          <PreviewSubhead>Cited by</PreviewSubhead>
          <ul className="pl-6 text-body">
            {cited.slice(0, 5).map((doc) => (
              <PreviewRow key={doc.relPath}>
                <PreviewLink
                  mono={false}
                  onClick={() => onPreview({ kind: "knowledge", path: doc.relPath })}
                >
                  {doc.name}
                </PreviewLink>
              </PreviewRow>
            ))}
          </ul>
        </>
      ) : null}
    </PreviewFrame>
  );
};

export const ContentPreview = (props: ContentPreviewProps): JSX.Element => {
  const { target, snapshot, onPreview, onOpen, onOpenInBackground, onClose } = props;
  if (target.kind === "file") {
    return (
      <FilePreview
        target={target}
        onOpen={onOpen}
        onOpenInBackground={onOpenInBackground}
        onClose={onClose}
      />
    );
  }
  if (target.kind === "knowledge") {
    return (
      <DocumentPreview
        target={target}
        onPreview={onPreview}
        onOpen={onOpen}
        onOpenInBackground={onOpenInBackground}
        onClose={onClose}
      />
    );
  }
  const asset = snapshot.assets.find((item) => item.id === target.assetId) ?? null;
  const frame = {
    title: asset?.name ?? target.assetId,
    mono: true,
    onOpen: () => onOpen(target),
    onOpenInBackground,
    onClose,
  };
  if (!asset) return <PreviewGone {...frame} kindLabel="asset" />;
  const producer = asset.runId ? snapshot.runs.find((run) => run.id === asset.runId) : undefined;
  const download = asset.projectId ? assetsApi.downloadUrl(asset.projectId, asset.id) : null;
  return (
    <PreviewFrame
      {...frame}
      lead={<KindIcon icon={entityMeta("asset").icon} />}
      context={["asset", asset.sizeBytes !== null ? formatBytes(asset.sizeBytes) : null]
        .filter(Boolean)
        .join(" · ")}
      copies={[
        { label: "Asset id", value: asset.id },
        ...(asset.ref ? [{ label: "Reference", value: asset.ref }] : []),
      ]}
      actions={
        download ? (
          <WorkbenchAction
            kind="secondary"
            size="content"
            className="h-shell-button rounded-hairline bg-interactive px-3 font-normal"
            asChild
          >
            <a href={download} download>
              Download
            </a>
          </WorkbenchAction>
        ) : undefined
      }
    >
      <div className="pl-6">
        <PreviewKV label="kind" mono={false}>
          {asset.kind}
        </PreviewKV>
        {producer ? (
          <PreviewKV label="produced by" mono={false}>
            <PreviewLink
              onClick={() =>
                onPreview({
                  kind: "run",
                  runId: producer.id,
                  projectId: producer.projectId,
                  experimentId: producer.experimentId,
                })
              }
            >
              {runLabel(producer)}
            </PreviewLink>
          </PreviewKV>
        ) : null}
        {asset.summary ? (
          <PreviewKV label="summary" mono={false}>
            {asset.summary}
          </PreviewKV>
        ) : null}
      </div>
    </PreviewFrame>
  );
};
