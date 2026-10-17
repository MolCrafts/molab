---
name: molab-plan
description: >
  Interactive molab experiment planner. Decompose a research intent into a
  grounded task board, confirm each step with the user, then scaffold a molab
  experiment and write workflow code against APIs you have actually read.
  Use when the user wants to plan, design, or set up an experiment, sweep,
  screening study, or workflow — or when they run /molab-plan.
when-to-use: >
  Load when the user wants to plan, design, or scaffold a computational
  chemistry experiment, sweep, screening study, or workflow. Also when they
  run /molab-plan.
user-invocable: true
disable-model-invocation: false
metadata:
  author: MolCrafts
  short-description: Stepwise experiment planner; confirm, then execute that step.
---

# molab-plan

Interactive planner. **One step per turn:** propose, wait for confirm, execute
only that step.

## Grounding — read the API, never recall it

There is no discovery tool in this loop. Every symbol you put on the board is
one you have **opened in the installed source**:

- find it: `python -c "import molpy, pathlib; print(pathlib.Path(molpy.__file__).parent)"`
  then Grep/Read under that path — the installed version is the only one that
  matters, not the one on GitHub, not the one you remember
- record `file:line` (or the dotted qualname plus the file you read) as the
  task's `ref`
- group knowledge — protocols, past decisions, lab conventions — comes from
  `molab knowledge search <query>` and `molab knowledge read <id>`, not from
  memory

**A symbol you cannot find in the installed source does not exist.** Say which
package you searched and what you searched for, then stop. Do not approximate
a name, and do not write code around a signature you have not read.

## Hard rules

- **One step per turn.** Never fill the whole board in one go.
- **No writes before confirm.** Propose in chat; wait for yes / ok / an edit.
  An edit revises the proposal; confirm again before executing.
- **Do not close open questions** unless the user closes them.
- **Do not invent APIs.** A missing capability is a product gap: report what
  you searched, what you found instead, and wait.
- **Planning does not run science.** Long or destructive work (job submission,
  deletes, overwriting a run) needs its own explicit confirm, every time.

## Turns

End every planning turn with the proposal and a confirm prompt. Stop there.

### 1. Frame

Restate the objective in the user's words. List open questions (keep them
open). Propose. Wait.

On confirm: write them into the working plan (chat; and `plan.md` once an
experiment folder exists).

### 2. Focus

Read the workspace as it is: `molab project list`, `molab experiment list`
(add `--help` for the flags that version takes). Propose which project and
experiment. Wait.

On confirm: create what is missing — `molab experiment create …` — or, when
there is no workspace yet, `molab init <path>`. If molab is not installed,
keep the plan in chat and files, and say so plainly.

### 3. One task

Ground the **next** step only, per the rules above. Propose **one** task: id,
name, purpose, the `ref` you read, non-empty acceptance. The user names the
next step — do not force build → simulate → measure. Wait.

On confirm: append that task to the board in chat and in `plan.md`. Do not
place the rest.

Repeat until the user says the board is enough.

### 4. Realize one (only if asked)

Propose code for **one** confirmed task, using only refs you have read. Wait.

On confirm: write that file. Then check it the cheapest way that can actually
fail — import the module and inspect the signature you relied on
(`python -c "import inspect, pkg; print(inspect.signature(pkg.thing))"`).
Still no invented symbols.

### 5. Run one (only if asked)

Tell the user how (`molab exec` / `molab runs …`, or the queue command they
already use). Do not start a run or submit a job until they confirm that
action.

## Board

Each task has:

- `id`, `name`, `purpose`
- `ref` — the symbol you read, with the file it came from
- `acceptance` — one or more strings a later check could test

The board plus objective, open questions, and inferred-vs-stated values **are**
the plan. Write `plan.md` under the experiment once you have a folder.
