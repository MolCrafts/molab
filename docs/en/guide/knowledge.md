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

Always construct a **concrete** class. The `Knowledge` base is a directory-form
Concept, so `Knowledge(host, name)` would land a directory rather than a markdown
file.

**A path is only how you find a document.** To open one you already have — from
a search, from `ls`, from a link in another document — use `Knowledge.open`,
which reads the class back from the frontmatter:

```python
from molab.knowledge import Knowledge, Note

doc = Knowledge.open(experiment.resolve() / "knowledges" / "analysis-notes.md")
assert type(doc) is Note  # the `class:` frontmatter is honoured
assert doc.read().startswith("# Analysis Notes")
```

`molab.knowledge.location.folder(host, name, of)` is that same derivation on its
own — `of` is the class, and the return is the **landed path**:

```python
from molab.knowledge.location import folder

assert Note(experiment, "Analysis Notes").path == folder(experiment, "Analysis Notes", Note)
```

## The six classes

Every class lands one markdown file; the `class:` frontmatter names which one:

| Class | `class:` frontmatter | Purpose |
|---|---|---|
| `Note` | `class: Note` | A free note |
| `Literature` | `class: Literature` | A reference; bib fields in frontmatter, PDFs pointed at, never copied |
| `Report` | `class: Report` | A written-up analysis, including a failed run's |
| `Finding` | `class: Finding` | A harvested scientific outcome |
| `Plan` | `class: Plan` | An experiment's or project's plan book |
| `Observation` | `class: Observation` | A recorded observation or standing choice |

`Report`, `Finding`, `Plan` and `Observation` require at least one `SourceRef`
at construction — they are sourced documents; `Note` and `Literature` do not.

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
run_record = Knowledge.open(experiment.resolve() / "knowledges" / "run-0001.md")
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
from molab.knowledge.sources import open_source

wiki = open_source("lab-wiki")
for doc in wiki.walk():
    print(type(doc).__name__, doc.path)
for hit in wiki.search("cooling").hits:
    print(hit.entry.title)
```

`qualify_run_id` stays as the permanent qualifier for a legacy bare run id. A source that is not the workspace uses its registered root as the container.
If a wiki's documents sit under `<wiki>/knowledges/`, re-register that directory
as the source root: `molab knowledge sources remove <name>`, then
`molab knowledge sources add <name> <wiki>/knowledges`.

## Migrating an existing tree

`molab migrate knowledge [WORKSPACE]` is opt-in. It moves legacy documents into `<host>/knowledges/<stem>.md`, keeping the original stem:

- `molab migrate knowledge` reads a host-level `*.md` whose frontmatter `class` names a knowledge class;
- `molab migrate knowledge` reads `references/<key>.md` and `references/<key>/literature.json` plus `index.md`;
- `molab migrate knowledge` reads the directory form `knowledges/<id>/<class>.json` plus `index.md`.

Relative links to projects, experiments, runs, executions and artifacts become entity references. A document-to-document link is rebased so it still resolves. Frontmatter `sources:` rows that can be qualified are folded into typed links. A row that is unresolved or ambiguous stays in the frontmatter, and the report names it. A name that is already taken lands as `<stem>-2`, `<stem>-3`, … and both files are kept. Attachments and any other unnamed file stay in place and are listed as leftovers.

`--dry-run` prints the same plan and writes nothing. A real run records one `knowledge.migrated` commit covering only the paths it touched. Run it again and it reports that nothing changed.

## Next

- For the workspace the knowledge lands in, see [Workspace Model](../concept/workspace.md).
- For the concrete Python API around records and assets, see [Workspace API](workspace-api.md).
- For reusable data and provenance, see [Assets and Reproducibility](../concept/assets-and-reproducibility.md).
