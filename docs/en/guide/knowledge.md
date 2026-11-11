# Knowledge and Cross-References

A project's knowledge is not a bag of independent documents. It is the **index
of the experiment knowledge beneath it** — the findings, reports, observations
and notes written under the project's experiments — held together by the
**plans** (`Plan`) and **summaries** (`Report` / `Finding`) that belong to those
experiments. The workspace records what was computed and why; knowledge records
what it *means*.

There is no second notes database and no central index: the filesystem is the
database. A document is a markdown file, and its path is its identity.

## Where a document lives

Built-in knowledge lands as **one markdown file** under a `knowledges/`
container. A project's index sits beside its experiments; each experiment's
conclusions sit under the experiment:

```text
lab/projects/polymer-cg/
├── knowledges/tg-index.md                   ← a project's index of its experiments
└── experiments/solvation-sweep/
    └── knowledges/tg-result.md              ← one experiment's finding
```

`.md` is the form molab writes; a `.mdx` file is accepted on read only.

Everything that is not narrative lives in the file's YAML frontmatter, above all
the **`class`** that says which Knowledge class the document is:

```yaml
---
class: Finding
tags: [thermal]
---
```

## Constructing and finding a document

Construction names a **host** and a **name**; the host is a workspace `Folder`,
and the class derives its own path from them:

```python
from molab.knowledge import Note
from molab.workspace import Workspace

ws = Workspace("./lab", name="Lab")
ws.materialize()
experiment = ws.add_project("polymer-cg").add_experiment("solvation-sweep")

note = Note(experiment, "Analysis Notes")  # binds the path; touches no disk
note.write("# Analysis Notes\n\nQuench at 10 K/ns.\n")
```

`Note(experiment, "Analysis Notes").path` is
`<experiment>/knowledges/analysis-notes.md`, and that is where `write` puts the
bytes. Bind a name and nothing touches disk until the first write.

Always construct a **concrete** class. `Knowledge(host, name)` raises
`TypeError`: the base is not a document, and it does not construct a subclass.

**A path is the same constructor.** A file you already have — from a search,
from `ls`, from a link — is `Note(path)` when you know it is a note. A sourced
file that is already on disk is `Finding(path)` (no sources argument). The
base class does not read `class:` and return a different type.

```python
from molab.knowledge import Note

doc = Note(experiment.resolve() / "knowledges" / "analysis-notes.md")
assert type(doc) is Note
assert doc.read().startswith("# Analysis Notes")
assert Note(experiment, "Analysis Notes").path == doc.path
```

## The classes

A document belongs to exactly one class, and a class answers exactly one
question. A document that answers two questions is two documents. If a
statement could be filed under two classes, the definitions are wrong, not the
author. Every class lands one file; the `class:` frontmatter names which one:

| Class | The one question it answers | Record (frontmatter) | Never contains |
|---|---|---|---|
| `Plan` | What are we asking, in what scope, under what constraints? | none | stages, work items, criteria, the claims to test (those are Hypotheses) |
| `Hypothesis` | What do we claim will turn out to be true? | `verdict`: `open` \| `supported` \| `refuted` \| `unsettled` (default `open`) | the evidence itself (that is a Finding) |
| `Roadmap` | In what order is the work done? | `stages` | items, criteria, status |
| `Todo` | What work remains? | `items` | stages, criteria |
| `Milestone` | When is a stage closed? | `stage`, `criterion`, `status` (`open` \| `met` \| `missed`) | stages, items |
| `Observation` | What was observed or given, before any interpretation? | none | a choice (Decision), a conclusion (Finding) |
| `Decision` | What was chosen, by whom, and why? | `status`: `open` \| `made` (default `made`) | an observed fact, a result |
| `Finding` | What does the evidence establish? | none | a choice, a plan |
| `Report` | What do we tell readers? It compiles; it claims nothing new. | none | a result stated nowhere else |
| `Literature` | What does a published source say? | bibliographic fields; PDFs pointed at, never copied | |
| `Delegation` | What supervised work is under way? (operational) | the delegation record: scope, goal, authorized actions, budget and spend, acceptance and stop conditions, waits, worker attempts | |
| `Note` | None of the above: free text with no claim on the reasoning. | none | |

A standing choice is a `Decision`, not an `Observation`. A `Report` is defined
by its purpose (telling readers), not by its length: a result written up at
length is still a `Finding`.

A `verdict` or `status` outside its vocabulary is refused on write and
reported by `molab validate` (`knowledge.record`); it is never replaced by the
default.

Every class but `Note` and `Literature` requires at least one `SourceRef` at
construction — they are sourced documents.

Plan, Roadmap, Todo, and Milestone are one campaign and four jobs. A Plan does
not list stages. A Roadmap does not list work items. A Todo does not define the
stage order. A Milestone does not list the work. Roadmap, Todo, and Milestone
cite the Plan. `campaign_of(plan)` reads that set; `check_campaign` checks that
every todo and milestone names a stage the roadmap has.

### Control flow lives in the links and the records

There is no class per control structure. The reasoning is read from the typed
links and the record fields:

| Control flow | How knowledge says it |
|---|---|
| condition / judgement | a `Hypothesis` and its `verdict` |
| evidence for or against | a link with role `supports` or `contradicts`, from a `Finding` to a `Hypothesis` |
| pass / cannot tell | `verdict: unsettled` |
| iteration | a new document that `supersedes` the one it revises |
| decision point | a `Decision`; `status: open` means it waits for a person |
| dependency | `derived_from` |
| mention | `cites` (a source), `references` (anything else), `records` |

The edge roles are `derived_from`, `supersedes`, `supports`, `contradicts`,
`cites`, `records`, and `references`. A typed link is written
`- [@supports label](target)`; a link with no role is `references`. The roles
are a vocabulary only: molab does not check which classes a `supports` or
`contradicts` link joins.

## Cross-reference is what ties knowledge together

The body of a document is its narrative, and the markdown links in that body
**are** the knowledge graph. They are written with `.ref`, which takes another
**Knowledge** — a document object, or the on-disk path that locates one:

```python
from molab.knowledge import Finding, SourceRef

finding = Finding(experiment, "Tg Result", sources=[SourceRef(kind="run", ref="run-0001")])
finding.write("# Tg Result\n\nTg rose with cooling rate.\n")

note.ref(finding)  # by object…
note.ref(finding.path)  # …or by path — the same edge either way
```

`.ref` **never** takes a project / experiment / run coordinate: not a `Folder`,
not a run id, not params. Those are not knowledge, and `.ref` rejects them with
`TypeError`. To point at a run or an experiment, first find the document that
records it, then `.ref` that document:

```python
run_record = Note(experiment.resolve() / "knowledges" / "run-0001.md")
note.ref(run_record)
```

The edges are recomputable from the tree — nothing is stored twice, and there is
no separate backlink type:

```python
for edge in note.links():
    print(edge.role, edge.target)  # e.g. references …/knowledges/tg-result.md
```

`.cite` is the looser sibling: it delegates a Knowledge target to `.ref`, and
otherwise links the path it is handed as given.

## Writing into a workspace

Two module-level verbs write knowledge into a workspace tree, both hosted by a
`Folder`:

- `mount_note(host, name, *, body="")` — idempotently mount a `Note`; a repeat
  call never truncates an existing body.
- `write_knowledge(host, *, name, of, sources, created_by, text, cite=(), title="")`
  — write a sourced document, idempotent on `name`.

`Finding.harvest` (the same method on `Observation` and `Report`) turns a
finished run's outcome into knowledge under the run's experiment:

```python
from molab.knowledge import Finding

finding = Finding.harvest(
    run,
    narrative="Tg rose with cooling rate.",
    created_by="lin",
)
```

Only a **terminal** run (`succeeded` / `failed` / `cancelled` / `interrupted`)
can be harvested, and `narrative` must be non-empty — a harvest is an
interpretation, not an archive. The raw record already lives in the run's
`index.md` and the assets it registered. `created_by` is a required keyword
argument.

## Citing a registered asset

The prose is the narrative. The writer appends one source link per citation
and does not copy status, parameters, errors, or result values. Harvest cites
each asset the latest
attempt registered (`molab:asset/<id>`). A `results` entry whose value sits at
one point in those files is cited with that point as the span: `/loss` for a
JSON field, `loss@10000` for the series value at step 10000. A result with no
registered asset, or one that matches nothing or more than one point, is
refused. The next run takes its inputs from the document's `inputs`.
`read_cited` reads the value at a span. `read` returns the narrative.
The workflow that opens the files does not import knowledge.

```python
follow = experiment.add_run(inputs=finding.inputs)
finding.read_cited("/loss")  # 0.08, the value at that span
```

`GeneratedParts(run).list()` lists the image assets (media type `image/*`, or
a `part` tag) one attempt registered. It does not write a document. Cite the
asset from a harvest when the narrative uses it.

```python
from molab.knowledge import GeneratedParts

parts = GeneratedParts(run)
for part in parts.list():
    print(part.part, part.ref)
```

A task body cannot call it: `TaskContext` has no path up to the Run. After
`molab run`, list the parts with `molab knowledge parts`.

```console
$ molab knowledge parts <run-id> --path .
```

## Layering

`molab.knowledge` depends on `molab.workspace` — a document needs a host folder
to know where to land — and that dependency is one-way: `molab.workspace` never
names knowledge.

## Searching a group wiki

Knowledge need not live in a workspace. A lab wiki is a directory of documents;
register it as a named source and search it by keyword:

```console
$ molab knowledge init /data/group/wiki --title "Lab notes"
$ molab knowledge sources add lab-wiki /data/group/wiki
$ molab knowledge search "cooling rate for Tg"
$ molab knowledge read lab-wiki:tg-index
```

Retrieval is **BM25F** over title, tags, path and body, and hits from several
sources are fused by reciprocal rank fusion. Chinese text is tokenized into
unigrams *and* adjacent bigrams — no segmenter, no dictionary, no embeddings.
This is keyword ranking, not RAG.

In Python a registered source opens as a tree handle, whose `walk()` yields its
documents and whose `search(...)` ranks them:

```python
from molab.knowledge.sources import KnowledgeSourceStore

wiki = KnowledgeSourceStore().open("lab-wiki")
for doc in wiki.walk():
    print(type(doc).__name__, doc.path)
for hit in wiki.search("cooling").hits:
    print(hit.entry.title)
```

`qualify_run_id` stays as the permanent qualifier for a legacy bare run id. A source that is not the workspace uses its registered root as the container.
If a wiki's documents sit under `<wiki>/knowledges/`, re-register that directory
as the source root: `molab knowledge sources remove <name>`, then
`molab knowledge sources add <name> <wiki>/knowledges`.

## Current documents

A knowledge document is `<host>/knowledges/<slug>.md`. Old directory layouts and `references/` trees are not imported.

## Next

- For the workspace the knowledge lands in, see [Workspace Model](../concept/workspace.md).
- For the concrete Python API around records and assets, see [Workspace API](workspace-api.md).
- For reusable data and provenance, see [Assets and Reproducibility](../concept/assets-and-reproducibility.md).

## Delegations and structured records

A `Delegation` is the record a supervising agent (for example Tack) keeps for one
piece of work. Its frontmatter is validated by
`molab.knowledge.delegation.DelegationRecord`: `kind`, `goal`, `scope` (a
`molab:` ref), `actions` (a closed set: `read`, `create_experiment`,
`create_run`, `start_execution`, `cancel_execution`, `write_knowledge`,
`delegate_worker`), `budget` / `spent`, `acceptance`, `stop_conditions`,
`state` (`open` / `waiting` / `blocked` / `paused` / `done` / `stopped`),
`waits`, `attempts`, `supervisor`, `current_plan`, `questions`, `amendments`,
`writes`, `last_decision`, `answers` and `approvals` (what a person approved
at each human gate — `parameters`, `plan`, `dry_run` or `results` — and the
knowledge path, experiment path or `molab:` ref it is about). Its source is
the scope it is bound to.

A document whose class owns a record (Delegation, Roadmap, Todo, Milestone,
Hypothesis, Decision) can have that record replaced whole over HTTP:

- `GET /api/knowledge/doc/record?path=…` returns `{record, digest}`.
- `PATCH /api/knowledge/doc/record?path=…` with `{record, ifMatch, body?}`
  replaces it; a stale `ifMatch` answers 409, an invalid record 422. Each
  replacement is a `knowledge.record_replaced` history commit.

`POST …/runs/{run}/executions` accepts `requestKey` (idempotency: the same key
returns the attempt already created) and `requestedBy` (the software agent
recorded as the attempt's creator).
