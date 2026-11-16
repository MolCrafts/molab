import { Button, Input, Label } from "@molcrafts/ui";
import { type QueryFilters, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Folder, Share2 } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { sharingApi } from "@/api/sharing";
import type { Principal, PublishedRun, SharedProject } from "@/api/sharing-generated";
import { StatusIcon } from "@/app/components/entity/StatusIcon";
import { useConfirm } from "@/components/ConfirmDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { CHART_SERIES_PALETTE } from "@/lib/chart-tokens";
import { formatDateTime } from "@/lib/datetime";
import { AssetSharingPanel } from "./AssetSharingPanel";
import { PublicationPage } from "./PublicationPage";

const LineChart = lazy(() =>
  import("@/plugins/molplot/MolplotLineChart").then((module) => ({
    default: module.MolplotLineChart,
  })),
);

export const isSharingPath = (pathname: string): boolean =>
  /^\/(?:shared|publish)(?:\/|$)/.test(pathname);

export function SharingApp(): JSX.Element {
  const session = useQuery({
    queryKey: ["sharing-session"],
    queryFn: ({ signal }) => sharingApi.me(signal),
    refetchInterval: 3000,
    retry: false,
    gcTime: 0,
  });
  const queryClient = useQueryClient();
  const principalId = session.data?.id;
  useEffect(() => {
    return () => {
      const protectedQueries: QueryFilters = {
        predicate: (query) =>
          query.queryKey[0] !== "sharing-session" &&
          (query.queryKey[0] !== "sharing" || query.queryKey[1] === principalId),
      };
      void queryClient.cancelQueries(protectedQueries);
      queryClient.removeQueries(protectedQueries);
      queryClient.getMutationCache().clear();
    };
  }, [principalId, queryClient]);
  useEffect(() => {
    if (session.isError) {
      const protectedQueries: QueryFilters = {
        predicate: (query) => query.queryKey[0] !== "sharing-session",
      };
      void queryClient.cancelQueries(protectedQueries);
      queryClient.removeQueries(protectedQueries);
      queryClient.getMutationCache().clear();
    }
  }, [session.isError, queryClient]);
  if (session.isPending)
    return (
      <p className="p-6" role="status">
        Checking cluster identity…
      </p>
    );
  if (session.isError)
    return (
      <p className="p-6" role="alert">
        {session.error.message}
      </p>
    );
  return <SharedSession key={session.data.id} principal={session.data} />;
}

function SharedSession({ principal }: { principal: Principal }): JSX.Element {
  const location = useLocation();
  const projectId = /^\/shared\/projects\/([^/]+)$/.exec(location.pathname)?.[1];
  return (
    <main className="min-h-screen bg-background text-body text-foreground">
      <nav aria-label="Sharing" className="flex flex-wrap items-center gap-4 border-b px-4 py-3">
        <Link to="/shared" className="flex items-center gap-2 font-medium">
          <Share2 className="size-icon" aria-hidden />
          Shared with me
        </Link>
        <Link to="/publish" className="text-muted-foreground hover:text-foreground">
          Publish a project
        </Link>
        <a href="/projects" className="text-muted-foreground hover:text-foreground">
          My workspace
        </a>
        <span className="ml-auto text-label text-muted-foreground">{principal.display_name}</span>
        <details className="relative text-label">
          <summary className="cursor-pointer">My sharing ID</summary>
          <code className="absolute right-0 z-10 mt-2 whitespace-nowrap border bg-background p-3">
            {principal.id}
          </code>
        </details>
      </nav>
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        {location.pathname === "/publish" ? (
          <PublicationPage principal={principal} />
        ) : projectId ? (
          <SharedProjectPage key={projectId} principal={principal} projectId={projectId} />
        ) : (
          <SharedProjects principal={principal} />
        )}
      </div>
    </main>
  );
}

function SharedProjects({ principal }: { principal: Principal }): JSX.Element {
  const [offset, setOffset] = useState(0);
  const client = useQueryClient();
  const projects = useQuery({
    queryKey: ["sharing", principal.id, "projects", offset],
    queryFn: ({ signal }) => sharingApi.projects(offset, signal),
    refetchInterval: 3000,
    retry: false,
    gcTime: 0,
  });
  const invitations = useQuery({
    queryKey: ["sharing", principal.id, "invitations"],
    queryFn: ({ signal }) => sharingApi.invitations(signal),
    refetchInterval: 3000,
    retry: false,
    gcTime: 0,
  });
  const respond = useMutation({
    gcTime: 0,
    mutationFn: ({ id, accept }: { id: string; accept: boolean }) => sharingApi.respond(id, accept),
    onSuccess: () => client.invalidateQueries({ queryKey: ["sharing", principal.id] }),
  });
  return (
    <>
      <PageHeader icon={Share2} title="Shared projects" />
      <p className="my-4 text-muted-foreground">
        Review experiments and published results from your collaborators.
      </p>
      {respond.isError && <p role="alert">{respond.error.message}</p>}
      {invitations.isError ? (
        <p role="alert">{invitations.error.message}</p>
      ) : (
        invitations.data
          ?.filter((i) => i.status === "pending")
          .map((invitation) => (
            <div key={invitation.id} className="my-3 flex flex-wrap items-center gap-3 border p-3">
              <div className="min-w-0 flex-1">
                <p>
                  {invitation.project_name ?? "Project invitation"}
                  {invitation.owner_name ? ` · ${invitation.owner_name}` : ""}
                </p>
                <p className="text-label text-muted-foreground">
                  Expires {formatDateTime(invitation.expires_at)}
                </p>
              </div>
              <Button
                disabled={
                  respond.isPending || new Date(invitation.expires_at).getTime() <= Date.now()
                }
                onClick={() => respond.mutate({ id: invitation.id, accept: true })}
              >
                Accept
              </Button>
              <Button
                variant="outline"
                disabled={respond.isPending}
                onClick={() => respond.mutate({ id: invitation.id, accept: false })}
              >
                Decline
              </Button>
            </div>
          ))
      )}
      {projects.isError ? (
        <p role="alert">{projects.error.message}</p>
      ) : projects.isPending ? (
        <p role="status">Loading shared projects…</p>
      ) : (
        <>
          {projects.data.items.length === 0 && (
            <p className="border-y py-8 text-muted-foreground">
              No shared projects yet. Give a collaborator your sharing ID to receive an invitation.
            </p>
          )}
          <ul className="divide-y border-y">
            {projects.data.items.map((project) => (
              <li key={project.id}>
                <Link
                  to={`/shared/projects/${project.id}`}
                  className="flex items-center gap-3 py-4 focus-visible:outline focus-visible:outline-primary"
                >
                  <Folder className="size-icon text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {project.project?.name ?? "Unpublished project"}
                    </p>
                    <p className="text-label text-muted-foreground">
                      {project.owner_name} · {project.role}
                    </p>
                  </div>
                  <span className="text-label text-muted-foreground">
                    {project.active ? formatDateTime(project.published_at) : "Publication stopped"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {projects.data.total > 100 && (
            <div className="mt-3 flex items-center gap-3 text-label">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous
              </Button>
              <span>{projects.data.total} projects</span>
              <Button
                variant="outline"
                disabled={offset + 100 >= projects.data.total}
                onClick={() => setOffset(offset + 100)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}

function SharedProjectPage({
  principal,
  projectId,
}: {
  principal: Principal;
  projectId: string;
}): JSX.Element {
  const navigate = useNavigate();
  const project = useQuery({
    queryKey: ["sharing", principal.id, "project", projectId],
    queryFn: ({ signal }) => sharingApi.project(projectId, signal),
    refetchInterval: 3000,
    retry: false,
    gcTime: 0,
  });
  const { confirm, dialog } = useConfirm();
  const leave = useMutation({
    gcTime: 0,
    mutationFn: () => sharingApi.remove(projectId, principal.id),
    onSuccess: () => navigate("/shared"),
  });
  if (project.isError) return <p role="alert">{project.error.message}</p>;
  if (project.isPending) return <p role="status">Loading published results…</p>;
  const data = project.data;
  return (
    <>
      <Link to="/shared" className="text-label text-muted-foreground">
        ← Shared projects
      </Link>
      <PageHeader
        title={data.project?.name ?? "Unpublished project"}
        icon={Folder}
        actions={
          data.role === "viewer" ? (
            <Button
              variant="outline"
              disabled={leave.isPending}
              onClick={async () => {
                if (
                  await confirm({
                    title: "Leave this project?",
                    description: "Ask the owner for another invitation to rejoin.",
                    confirmLabel: "Leave project",
                  })
                )
                  leave.mutate();
              }}
            >
              Leave project
            </Button>
          ) : undefined
        }
      />
      <p className="my-3 text-label text-muted-foreground">
        {data.owner_name} · {data.role} · Published {formatDateTime(data.published_at)}
      </p>
      {(!data.source_seen_at || Date.now() - new Date(data.source_seen_at).getTime() > 60000) && (
        <p className="mb-3 text-label text-muted-foreground">
          Showing the last published version. The owner's service may be offline.
        </p>
      )}
      {!data.active && (
        <p className="mb-3" role="status">
          Publication stopped. Only you can view this saved version.
        </p>
      )}
      {data.project?.description && (
        <p className="my-4 whitespace-pre-wrap">{data.project.description}</p>
      )}
      {leave.isError && <p role="alert">{leave.error.message}</p>}
      {data.version_id && (
        <>
          <PublishedExperiments
            key={`experiments:${data.version_id}`}
            principal={principal}
            project={data}
          />
          <PublishedRuns key={data.version_id} principal={principal} project={data} />
        </>
      )}
      <AssetSharingPanel principal={principal} project={data} />
      {data.role === "owner" && <SharingMembers principal={principal} project={data} />}
      {dialog}
    </>
  );
}

function PublishedExperiments({
  principal,
  project,
}: {
  principal: Principal;
  project: SharedProject;
}): JSX.Element {
  const [offset, setOffset] = useState(0);
  const experiments = useQuery({
    queryKey: ["sharing", principal.id, project.id, project.version_id, "experiments", offset],
    queryFn: ({ signal }) => sharingApi.experiments(project.id, offset, signal),
    retry: false,
    gcTime: 0,
  });
  if (experiments.isError) return <p role="alert">{experiments.error.message}</p>;
  if (experiments.isPending) return <p role="status">Loading experiments…</p>;
  return (
    <section className="my-6" aria-label="Published experiments">
      <h2 className="mb-3 font-medium">Experiments · {experiments.data.total}</h2>
      <ul className="divide-y border-y">
        {experiments.data.items.map((experiment) => (
          <li key={experiment.id} className="py-3">
            <p>{experiment.name}</p>
            {experiment.description && (
              <p className="mt-2 whitespace-pre-wrap text-muted-foreground">
                {experiment.description}
              </p>
            )}
          </li>
        ))}
      </ul>
      {experiments.data.total > 100 && (
        <div className="mt-3 flex gap-2">
          <Button variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - 100)}>
            Previous
          </Button>
          <Button
            variant="outline"
            disabled={offset + 100 >= experiments.data.total}
            onClick={() => setOffset(offset + 100)}
          >
            Next
          </Button>
        </div>
      )}
    </section>
  );
}

function PublishedRuns({
  principal,
  project,
}: {
  principal: Principal;
  project: SharedProject;
}): JSX.Element {
  const [offset, setOffset] = useState(0);
  const runs = useQuery({
    queryKey: ["sharing", principal.id, project.id, project.version_id, "runs", offset],
    queryFn: ({ signal }) => sharingApi.runs(project.id, offset, signal),
    retry: false,
    gcTime: 0,
  });
  if (runs.isError) return <p role="alert">{runs.error.message}</p>;
  if (runs.isPending) return <p role="status">Loading runs…</p>;
  return (
    <section aria-label="Published runs" className="my-6">
      <h2 className="mb-3 font-medium">Runs · {runs.data.total}</h2>
      {runs.data.items.length === 0 && (
        <p className="text-muted-foreground">The owner has not published any runs.</p>
      )}
      <div className="divide-y border-y">
        {runs.data.items.map((run) => (
          <PublishedRunRow key={`${run.experiment_id}/${run.id}`} run={run} />
        ))}
      </div>
      {runs.data.total > 100 && (
        <div className="mt-3 flex gap-2">
          <Button variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - 100)}>
            Previous
          </Button>
          <Button
            variant="outline"
            disabled={offset + 100 >= runs.data.total}
            onClick={() => setOffset(offset + 100)}
          >
            Next
          </Button>
        </div>
      )}
    </section>
  );
}

function PublishedRunRow({ run }: { run: PublishedRun }): JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <details className="py-3" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer">
        <span className="inline-flex items-center gap-2">
          <StatusIcon status={run.status} />
          <span className="font-mono text-label">{run.name}</span>
          <span className="text-label text-muted-foreground">{run.status}</span>
        </span>
      </summary>
      {open && (
        <>
          <dl className="my-3 grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 text-label">
            {Object.entries(run.parameters ?? {}).map(([key, value]) => (
              <div className="contents" key={key}>
                <dt className="text-muted-foreground">{key}</dt>
                <dd className="break-words">{String(value)}</dd>
              </div>
            ))}
          </dl>
          {Object.entries(run.metrics ?? {}).map(([key, points]) => (
            <figure key={key} className="my-4">
              <figcaption className="mb-2 text-label">
                {key} · {points.length} points · latest {points.at(-1)?.value ?? "—"}
              </figcaption>
              {points.length > 0 && (
                <Suspense fallback={<p role="status">Loading chart…</p>}>
                  <LineChart
                    key={`${key}:${points.length}:${points.at(-1)?.value}`}
                    config={{
                      series: [
                        {
                          id: key,
                          label: key,
                          color: CHART_SERIES_PALETTE[0],
                          initialPoints: points.map((point, index) => ({
                            x: point.step ?? index,
                            y: point.value,
                          })),
                        },
                      ],
                      xAxis: { label: "Step", type: "linear" },
                      yAxis: { label: key, type: "linear" },
                    }}
                    style={{ height: 220 }}
                  />
                </Suspense>
              )}
            </figure>
          ))}
        </>
      )}
    </details>
  );
}

function SharingMembers({
  principal,
  project,
}: {
  principal: Principal;
  project: SharedProject;
}): JSX.Element {
  const [recipient, setRecipient] = useState("");
  const client = useQueryClient();
  const members = useQuery({
    queryKey: ["sharing", principal.id, project.id, "members"],
    queryFn: ({ signal }) => sharingApi.members(project.id, signal),
    refetchInterval: 3000,
    retry: false,
    gcTime: 0,
  });
  const action = useMutation({
    gcTime: 0,
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: () => client.invalidateQueries({ queryKey: ["sharing", principal.id] }),
  });
  const { confirm, dialog } = useConfirm();
  return (
    <section className="mt-8 border-t pt-4" aria-label="Manage sharing">
      <h2 className="mb-3 font-medium">Manage sharing</h2>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          action.mutate(() => sharingApi.invite(project.id, recipient.trim()));
        }}
      >
        <div className="min-w-56 flex-1">
          <Label htmlFor="sharing-recipient">Recipient's sharing ID</Label>
          <Input
            id="sharing-recipient"
            required
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
            placeholder="Ask your collaborator for their ID"
          />
        </div>
        <Button type="submit" disabled={action.isPending || !recipient.trim()}>
          Invite viewer
        </Button>
      </form>
      {action.isError && (
        <p role="alert" className="mt-3">
          {action.error.message}
        </p>
      )}
      {members.isError ? (
        <p role="alert">{members.error.message}</p>
      ) : (
        <ul className="my-4 divide-y">
          {members.data?.members.map((member) => (
            <li key={member.principal_id} className="flex items-center gap-3 py-2">
              <span className="flex-1">{member.display_name} · Viewer</span>
              <Button
                variant="outline"
                disabled={action.isPending}
                onClick={() =>
                  action.mutate(() => sharingApi.remove(project.id, member.principal_id))
                }
              >
                Remove
              </Button>
            </li>
          ))}
          {members.data?.invitations.map((invitation) => (
            <li key={invitation.id} className="flex flex-wrap items-center gap-3 py-2">
              <span className="flex-1 break-all text-label">
                Invitation to {invitation.recipient_id}
              </span>
              <Button
                variant="outline"
                disabled={action.isPending}
                onClick={() => action.mutate(() => sharingApi.revokeInvitation(invitation.id))}
              >
                Cancel invitation
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Button
        variant="outline"
        disabled={action.isPending || !project.active}
        onClick={async () => {
          if (
            await confirm({
              title: "Stop publishing this project?",
              description:
                "Viewers lose access. Publish again from your workspace to resume sharing.",
              confirmLabel: "Stop publishing",
              destructive: true,
            })
          )
            action.mutate(() => sharingApi.stop(project.id));
        }}
      >
        Stop publishing
      </Button>
      {dialog}
    </section>
  );
}
