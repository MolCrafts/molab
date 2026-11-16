import { Button, Input, Label } from "@molcrafts/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { sharingApi } from "@/api/sharing";
import type { Principal, PublicationSelection } from "@/api/sharing-generated";
import { PageHeader } from "@/components/layout/PageHeader";

export function PublicationPage({ principal }: { principal: Principal }): JSX.Element {
  const inventory = useQuery({
    queryKey: ["sharing", principal.id, "worker-inventory"],
    queryFn: ({ signal }) => sharingApi.inventory(signal),
    retry: false,
    gcTime: 0,
  });
  const [selection, setSelection] = useState<PublicationSelection>({ project_id: "" });
  const review = useMutation({
    gcTime: 0,
    mutationFn: async (chosen: PublicationSelection) => ({
      selection: chosen,
      ...(await sharingApi.preview(chosen)),
    }),
  });
  const publish = useMutation({
    gcTime: 0,
    mutationFn: ({ chosen, digest }: { chosen: PublicationSelection; digest: string }) =>
      sharingApi.publish(chosen, digest),
  });
  const project = inventory.data?.find((p) => p.id === selection.project_id);
  const approved = review.data?.selection === selection ? review.data : null;
  const parameterKeys = [
    ...new Set(project?.experiments.flatMap((e) => e.runs.flatMap((r) => r.parameter_keys)) ?? []),
  ];
  const toggle = (values: string[] | undefined, value: string, checked: boolean): string[] =>
    checked ? [...(values ?? []), value] : (values ?? []).filter((item) => item !== value);

  return (
    <>
      <PageHeader title="Publish project results" />
      <p className="my-4 text-muted-foreground">
        Choose the experiments, runs and values your collaborators can see. Review the exact data
        before publishing.
      </p>
      {inventory.isError ? (
        <p role="alert">
          Your workspace service is unavailable. Open this page through your cluster's Molab entry
          point.
        </p>
      ) : inventory.isPending ? (
        <p role="status">Loading your projects…</p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            publish.reset();
            review.mutate(selection);
          }}
        >
          <fieldset disabled={publish.isPending} className="space-y-4">
            <div>
              <Label htmlFor="publication-project">Project</Label>
              <select
                id="publication-project"
                required
                className="mt-1 block h-9 w-full rounded-md border bg-background px-3"
                value={selection.project_id}
                onChange={(event) => {
                  setSelection({ project_id: event.target.value });
                  publish.reset();
                }}
              >
                <option value="">Choose a project</option>
                {inventory.data.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            {project && (
              <>
                <fieldset className="divide-y border-y">
                  <legend className="pb-2 font-medium">Experiments and runs</legend>
                  {project.experiments.map((experiment) => (
                    <div key={experiment.id} className="py-3">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selection.experiment_ids?.includes(experiment.id) ?? false}
                          onChange={(event) => {
                            const checked = event.target.checked;
                            setSelection({
                              ...selection,
                              experiment_ids: toggle(
                                selection.experiment_ids,
                                experiment.id,
                                checked,
                              ),
                              run_refs: checked
                                ? selection.run_refs
                                : selection.run_refs?.filter(
                                    (ref) => !experiment.runs.some((r) => r.ref === ref),
                                  ),
                            });
                          }}
                        />
                        {experiment.name}
                      </label>
                      {selection.experiment_ids?.includes(experiment.id) && (
                        <div className="ml-6 mt-2 space-y-2">
                          {experiment.runs.map((run) => (
                            <label key={run.ref} className="flex items-center gap-2 text-label">
                              <input
                                type="checkbox"
                                checked={selection.run_refs?.includes(run.ref) ?? false}
                                onChange={(event) =>
                                  setSelection({
                                    ...selection,
                                    run_refs: toggle(
                                      selection.run_refs,
                                      run.ref,
                                      event.target.checked,
                                    ),
                                  })
                                }
                              />
                              <span className="break-all">{run.name}</span>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </fieldset>
                <fieldset>
                  <legend className="mb-2 font-medium">Parameters to include</legend>
                  <div className="flex flex-wrap gap-4">
                    {parameterKeys.map((key) => (
                      <label key={key} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selection.parameter_keys?.includes(key) ?? false}
                          onChange={(event) =>
                            setSelection({
                              ...selection,
                              parameter_keys: toggle(
                                selection.parameter_keys,
                                key,
                                event.target.checked,
                              ),
                            })
                          }
                        />
                        {key}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div>
                  <Label htmlFor="publication-metrics">
                    Numeric metric names, separated by commas
                  </Label>
                  <Input
                    key={project.id}
                    id="publication-metrics"
                    defaultValue=""
                    onChange={(event) =>
                      setSelection({
                        ...selection,
                        metric_keys: event.target.value
                          .split(",")
                          .map((key) => key.trim())
                          .filter(Boolean),
                      })
                    }
                    placeholder="For example: energy, temperature"
                  />
                  <p className="mt-1 text-label text-muted-foreground">
                    Only these recorded numeric series will be included, up to 2,000 points each.
                  </p>
                </div>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selection.include_descriptions ?? false}
                    onChange={(event) =>
                      setSelection({ ...selection, include_descriptions: event.target.checked })
                    }
                  />
                  Include project and experiment descriptions
                </label>
              </>
            )}
            <Button type="submit" disabled={!project || review.isPending}>
              Preview shared data
            </Button>
          </fieldset>
        </form>
      )}
      {review.isError && (
        <p role="alert" className="mt-4">
          {review.error.message}
        </p>
      )}
      {approved && (
        <section aria-label="Publication preview" className="mt-6 border-t pt-4">
          <h2 className="font-medium">Review: {approved.preview.project.name}</h2>
          <p className="my-2 text-muted-foreground">
            {approved.preview.experiments.length} experiments · {approved.preview.runs.length} runs.
            New runs and metrics will require another review.
          </p>
          <details className="my-4">
            <summary className="cursor-pointer">Review all values that will be shared</summary>
            <pre className="mt-3 max-h-96 overflow-auto rounded-md border bg-muted p-3 text-label">
              {JSON.stringify(approved.preview, null, 2)}
            </pre>
          </details>
          <Button
            disabled={publish.isPending}
            onClick={() => publish.mutate({ chosen: approved.selection, digest: approved.digest })}
          >
            Publish reviewed data
          </Button>
        </section>
      )}
      {publish.isError && (
        <p role="alert" className="mt-4">
          {publish.error.message}
        </p>
      )}
      {publish.isSuccess && (
        <p role="status" className="mt-4">
          Published.{" "}
          <Link className="underline" to={`/shared/projects/${publish.data.project_id}`}>
            Invite collaborators
          </Link>
        </p>
      )}
    </>
  );
}
