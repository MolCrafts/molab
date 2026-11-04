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

Every class lands one markdown file; the `class:` frontmatter names which one:

| Class | `class:` frontmatter | Purpose |
|---|---|---|
| `Note` | `class: Note` | A free note |
| `Literature` | `class: Literature` | A reference; bib fields in frontmatter, PDFs pointed at, never copied |
| `Report` | `class: Report` | A written-up analysis, including a failed run's |
| `Finding` | `class: Finding` | A harvested scientific outcome |
| `Plan` | `class: Plan` | Campaign overview: question, scope, constraints |
| `Roadmap` | `class: Roadmap` | Ordered stages, and which experiment each stage is |
| `Todo` | `class: Todo` | Work items and their status |
| `Milestone` | `class: Milestone` | One checkpoint: the stage it closes and the criterion |
| `Observation` | `class: Observation` | A recorded observation or standing choice |
| `Delegation` | `class: Delegation` | One bounded, resumable piece of supervised work: scope, goal, authorized actions, budget and spend, acceptance and stop conditions, waits, worker attempts |

`Report`, `Finding`, `Plan`, `Roadmap`, `Todo`, `Milestone`, and `Observation`
require at least one `SourceRef` at construction — they are sourced documents;
`Note` and `Literature` do not.

Plan, Roadmap, Todo, and Milestone are one campaign and four jobs. A Plan does
not list stages. A Roadmap does not list work items. A Todo does not define the
stage order. A Milestone does not list the work. Roadmap, Todo, and Milestone
cite the Plan. `campaign_of(plan)` reads that set; `check_campaign` checks that
every todo and milestone names a stage the roadmap has.

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

`harvest_run` turns a finished run's outcome into knowledge under the run's
experiment:

```python
from molab.knowledge import Finding, harvest_run

finding = harvest_run(
    run,
    of=Finding,
    narrative="Tg rose with cooling rate.",
    created_by="lin",
)
```

Only a **terminal** run (`succeeded` / `failed` / `cancelled`) can be harvested,
and `narrative` must be non-empty — a harvest is an interpretation, not an
archive; the raw record already lives in `run.json` and the run's artifacts.
`created_by` is a required keyword argument. `of` is typically `Finding`,
`Observation` or `Report`.

## Viewing generated image parts

Harvest inlines truncated result text. It does not show the images a run
emitted. `GeneratedParts(run).list()` lists those artifacts (media type `image/*`,
or a `part` tag; `result` and `checkpoint` artifacts are skipped).
`GeneratedParts(run).view(...)` writes a Report under the experiment. Each part is a
`records` link to its `molab:` artifact ref, and an image part is also a
relative `![]()` so a markdown preview can show the file. A `molab:` URL is
not itself an image.

```python
from molab.knowledge import GeneratedParts

parts = GeneratedParts(run)
for part in parts.list():
    print(part.part, part.path)

report = parts.view(
    narrative="The portrait split into hair, eyes, clothes, and mouth.",
    created_by="lin",
)
```

The same preconditions as harvest apply. A task body cannot call it:
`TaskContext` has no path up to the Run. After `molab run`, store the Report
with `molab knowledge parts --write`.

From a workspace root:

```console
$ molab knowledge parts <run-id> --path .
$ molab knowledge parts <run-id> --path . --write
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
`state` (`open` / `waiting` / `paused` / `done` / `stopped`), `waits`,
`attempts`, `supervisor`, and `current_plan`. Its source is the scope it is
bound to.

A document whose class owns a record (Delegation, Roadmap, Todo, Milestone)
can have that record replaced whole over HTTP:

- `GET /api/knowledge/doc/record?path=…` returns `{record, digest}`.
- `PATCH /api/knowledge/doc/record?path=…` with `{record, ifMatch, body?}`
  replaces it; a stale `ifMatch` answers 409, an invalid record 422. Each
  replacement is a `knowledge.record_replaced` history commit.

`POST …/runs/{run}/executions` accepts `requestKey` (idempotency: the same key
returns the attempt already created) and `requestedBy` (the software agent
recorded as the attempt's creator).
