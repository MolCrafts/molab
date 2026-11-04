# Working with Coding Agents

Coding agents such as Claude Code and Codex edit a workspace the way a person does, by writing files. Left alone they tend to put scripts and plots beside experiment records, hand-write records, and record finished cluster jobs by inventing files. molab handles this in two ways. It gives an agent a legal place for each of those jobs, and it checks every write against the same layout law its own writers obey.

## What an agent reads

`molab init` writes a root `AGENTS.md` (and a `CLAUDE.md` that imports it with an `@AGENTS.md` line). molab owns only the block between `<!-- molab:begin -->` and `<!-- molab:end -->`, which it renders from code: the layout tree, what each attempt directory is for, the six knowledge classes, the scratch contract, and a "to do this, run that" table of commands. Anything you write outside the markers is kept. `molab agents sync` refreshes the block. It also appends any missing managed rules to `.gitignore` and writes the validation baseline when there is none.

The guide tells an agent to start at `./index.md`. Each `index.md` frontmatter is that level's record plus a derived `index:` block, and `index.children[].path` leads down to every project, experiment and run. A run's `index.executions[]` lists its attempts, and `index.knowledges` lists a level's knowledge documents. The frontmatter belongs to molab, so an agent may edit only the body.

## Legal paths

| to | use |
|---|---|
| try something quickly | `projects/<p>/experiments/<e>/scratch/` |
| record a job that ran outside molab | `molab runs adopt P E RUN --product TASK=PATH --log FILE --job FILE --source FILE` |
| read or write a record's narrative | `molab index show` / `molab index write --from FILE` |
| write a knowledge document | `molab knowledge write NAME TEXT --on HOST --class CLASS --source SOURCE --record JSON --created-by AGENT` |
| preview what a workflow script would run, writing nothing | `molab workflow dry-run SCRIPT --json` |
| rebuild the derived index blocks | `molab index sync` |
| print into the run's record | `from molab import print` ([Tracking a Computation](tracking.md)) |
| record training data | `ctx.metrics.scalar(...)` ([Tracking a Computation](tracking.md#metrics)) |

`scratch/` is for quick tests only. Nothing in it is cited and it stays out of git. It is never listed as a child, and `molab validate` warns about entries older than 14 days. A long job, or anything a result depends on, becomes a run. When that job has already finished outside molab, `molab runs adopt` moves its files into the run's next attempt (`executions/eNN/`: products under `out/<task>/`, scheduler files under `jobs/`, the log as `run.log`, scripts under `source/`) and seals the record with the real start and end times. `--params` creates the run first when it does not exist yet. `molab scratch clean --older-than 7d` empties old scratch entries, and `--dry-run` lists them without deleting anything.

## The check

`molab check` is the one place the rules live. The `molab` command must be on
`PATH` for the hooks and for agents (`uv tool install molcrafts-molab`, or
`uv tool install --editable` from a checkout); a hook that cannot find it lets
the change through unchecked. The hooks in [molcrafts-harness](https://github.com/MolCrafts/molcrafts-harness) hold no rule of their own. They forward each event and act on molab's JSON verdict:

- before a write: `molab check path PATH --op write|edit --content-file F --json`
- before a shell command: `molab check command --command TEXT --cwd DIR --json`
- when a session starts: `molab check tree DIR --snapshot <session> --json`
- when it stops: `molab check tree DIR --since <session> --json`

`check command` names the files a shell command would write and asks `check path` about each one. The command is not executed. A command the grammar cannot read is allowed, and the stop check sees what it wrote.

`check path` refuses a write that molab owns: a change to a record's frontmatter, a new `index.md` record, a `<kind>.json` or `meta.json` record, an attempt's `execution.json`, logs, `source/`, `artifacts/`, `jobs/` or `checkpoints/`, or anything under `.molab/` or `.git/`. It also refuses a knowledge document without a known `class:` and a new file or directory at a level where that name is not legal. Every refusal names the molab command to use instead. Some writes are always allowed: `scratch/`, an attempt's `out/` and `work/`, `workflow.py`, `AGENTS.md`, `CLAUDE.md` and `.gitignore`. A solver's own `meta.json` or `run.json` under `out/` or `scratch/` counts as science payload, not as a record. An edit to a stray that already exists is allowed too, because that is old debt, not a new mess.

`check tree` holds a session only to the errors it added. The snapshot taken at the start is compared with the tree at the stop. When the snapshot is missing, the workspace baseline (`.molab/validate-baseline.json`) is used. When both are missing, nothing can be called new and the session is allowed.

The same report is available directly:

```bash
molab validate                    # everything
molab validate --update-baseline  # accept today's debt
molab validate --new-only         # only what the baseline lacks
```

The `check` commands exit 0 whenever molab itself worked. The verdict's `allowed` field decides:

```json
{"in_workspace": true, "allowed": false, "rule": "index.frontmatter",
 "reason": "The frontmatter of index.md is molab's record …",
 "command": "molab index write -p alpha -e sweep --run t=1 --from FILE",
 "path": "projects/alpha/experiments/sweep/runs/t=1/index.md", "issues": []}
```
