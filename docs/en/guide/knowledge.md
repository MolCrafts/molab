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

| Class | The one question it answers | Fields (`FIELDS`) | Never contains |
|---|---|---|---|
| `Plan` | What are we asking, in what scope, under what constraints? | none | stages, work items, criteria (Roadmap, Todo, Milestone); the claims to test (Hypotheses) |
| `Roadmap` | In what order is the work done? | `stages`: each `id`, `title`, optional `experiment`, `depends_on` (ids unique, every dependency a stage, no cycle) | work items, criteria |
| `Todo` | What work remains? | `items`: each `id`, `title`, `status` `open` \| `done` \| `blocked` (default `open`), optional `stage` (ids unique) | the stage order |
| `Milestone` | When is the work accepted? | `criterion` (required), `status` `open` \| `met` \| `missed` (default `open`), optional `stage` it closes, optional `checks` and their `measurements` | the work that meets it |
| `Hypothesis` | What do we claim will turn out to be true? | `verdict`: `open` \| `supported` \| `refuted` \| `unsettled` (default `open`) | the evidence itself (that is a Finding) |
| `Observation` | What was observed or given, before any interpretation? | none | a conclusion (Finding) |
| `Finding` | What does the evidence establish? | none | a choice, a plan |
| `Report` | What do we tell readers? It compiles; it claims nothing new. | none | a result stated nowhere else |
| `Literature` | What does a published source say? | `LiteratureFields`: the bibliography; PDFs pointed at, never copied | |
| `Decision` | What was chosen, by whom, and why? | `status`: `made` (default) \| `open` while it waits for a person | an observed fact (Observation), a result (Finding) |
| `Manuscript` | What do we submit for publication? A paper, in LaTeX. | none | a result no Finding states; a bibliography of its own |
| `Note` | None of the above: free text with no claim on the reasoning. | `status`: `proposed` (default) \| `active` (reviewed; set explicitly) \| `retired` | |

A `Report` is defined by its purpose (telling readers), not by its length: a
result written up at length is still a `Finding`.

A file whose `class:` is absent or names no class is not a document: it is not
listed, searched or opened, and `molab validate` reports it (`knowledge.class`).

### A Manuscript is LaTeX

A `Manuscript` is the one class stored as `knowledges/<slug>.tex`, and `.tex`
holds nothing else (`knowledge.class` reports either mismatch). The file
compiles as it stands: its record is a leading block of `%%` comment lines and
its sources are whole-line comments, so TeX skips both.

```latex
%% molab-record
%% {
%%   "class": "Manuscript",
%%   "name": "NaCl NEMD"
%% }
%% end molab-record
\documentclass{revtex4-2}
\begin{document}
Shear thinning of molten NaCl~\cite{petravic2003}.
\bibliography{references}
\end{document}
% - [@derived_from outline](outline.md)
```

Each `\cite` key is the file name of a `Literature` document in the
manuscript's level or a level above it (the project, then the workspace root).
That is its `cites` edge, so the Literature lists the Manuscript among its
backlinks. A key no Literature document answers is a `molab validate` error
(`knowledge.citation`). The bibliography has no file of its own:
`molab knowledge bib DOC --out references.bib` writes it from those documents
(`@article` when the Literature has a venue, `@misc` otherwise) and refuses to
write a partial one; `GET /api/knowledge/doc/bib?path=…` is the same verb, and
the web preview compiles the Manuscript with it. A comment line with a
markdown link is an edge; a link anywhere else in the LaTeX is not.

A key follows the Literature it names: renaming that document, or replacing
it (`molab knowledge write … --replaces`), rewrites the key in every
Manuscript that cites it, as it rewrites their markdown links. Moving it keeps
its name and so its key; moved to a level the Manuscript does not look in
(below it, or into a sibling), the key is left unresolved and
`knowledge.citation` names it.

`molab init` brings knowledge an older molab wrote up to these classes without
losing a value: a `Delegation` (retired) becomes a `Plan`, and a frontmatter
key the class does not declare (a delegation record, `holds_under`, a Todo's
`gaps`) moves to a fenced YAML block under `## Moved fields` at the end of the
narrative. A link to an attempt's record file
(`runs/<run>/executions/<x>/execution.json`) becomes that execution's `molab:`
ref, which is what anchors a `Report` or `Finding`. A declared key whose value
the class refuses is left for `molab validate` to report.

Beside its fields, every document's frontmatter carries the same keys:
`class`, `name`, `created_by`, `created_at`, `tags`. A key the class does not
declare, or a value its fields refuse (a `verdict` outside its vocabulary), is
refused on write and reported by `molab validate` (`knowledge.fields`); it is
never replaced by the default. A class's fields are a pydantic model, so a
subclass extends its parent's.

Every class but `Note` and `Literature` requires at least one `SourceRef` at
construction — they are sourced documents. A source is a `molab:` ref (it keeps
the entity's kind), an http(s) URL or a DOI (a `reference`), or a file path.
`molab knowledge write --source` and `sources` on `POST /api/knowledge/doc`
take these as plain strings; given none, a sourced class names its host.

A `Report` or a `Finding` rests on registered bytes: it must link at least one
`molab:` asset, run or execution. A write that does not is refused (422 over
HTTP), and `molab validate` reports a hand-written one (`knowledge.unanchored`).

That is one instance of a general rule: a write is refused exactly when
`molab validate` would report an error for the document it leaves. Besides an
unanchored `Report` or `Finding`, that is a frontmatter its class refuses
(`knowledge.fields`), a `localhost` or loopback link (`knowledge.ephemeral_link`),
a numbered name such as `notes-v2` (`knowledge.versioned_name`), and page
markup — `<!doctype`, `<html>`, `<head>`, `<body>`, `<iframe>`, `<script>` or
`<style>` outside code — in a markdown document (`knowledge.html_page`; an
`.html` document is the one meant to be a page). Nothing is written; over HTTP
the write is 422 and the message names each rule and the offending text. The
one rule that reads more than one document, `knowledge.stage` (below), is
reported by `molab validate` and the end-of-session check but refuses no write,
so a Todo may be written before its Roadmap.
Moving or renaming a document still relinks the documents that point at it,
even one that already breaks a rule.

A `Plan` asks the question and sets the scope and constraints. Its stage
order is a `Roadmap`, its work items a `Todo`, and each acceptance criterion a
`Milestone`; each of those cites the Plan (any link to the Plan's file). A
stage a `Todo` item or a `Milestone` names must be on a `Roadmap` that cites
the same Plan (`knowledge.stage`); a document that cites no Plan is not
checked. A Milestone's `stage` is optional: a reproduction checkpoint closes no
stage. The claims a Plan sets out to test are `Hypothesis` documents.

### A settled status rests on evidence

A Milestone whose criterion is a number declares it as a check, and molab does
the arithmetic:

```yaml
checks:
  - id: ffv            # unique in the Milestone
    span: /ffv         # where the number sits in a registered JSON file
    expected: 0.29
    tolerance: 0.01    # absolute; `relative: true` scales it by `expected`
    compare: within    # or at_most / at_least
    critical: true     # a failed non-critical check does not miss the Milestone
```

`molab knowledge evaluate DOC --measure ffv=molab:asset/<id>` reads the span
from that asset, records the value with the asset's ref and content digest
under `measurements`, links the asset, and writes the status: `met` when every
critical check passes, `missed` when a measured critical check fails, `open`
while one is unmeasured. The bytes must be a run's own: registered by an
attempt molab ran itself, in a run molab ran to success, and not swapped since
by `molab asset replace`. An imported file, an adopted attempt's file and the
file of a run that never succeeded measure nothing. A `met` or `missed`
typed by hand must agree with the measurements beside it, or the write is
refused (`knowledge.fields`); `evaluate` measures over one that does not.

`molab validate` then reads more than the document, so these rules are
reported and refuse no write:

| Rule | What it reports |
|---|---|
| `knowledge.milestone_evidence` | a measurement whose asset is gone, is no longer its run's own (as `evaluate` requires), changed since it was read, or holds another value at the span; a `met` / `missed` Milestone with no checks that neither links a `Finding` nor is linked by one |
| `knowledge.stage_order` | a `met` Milestone closes a stage while a Milestone of a stage it depends on is not `met` |
| `knowledge.verdict_evidence` | a `supported` Hypothesis that no `Finding` links as `supports`, or a `refuted` one that none links as `contradicts` |
| `knowledge.dangling_ref` | a `Report` or `Finding` links a `molab:` ref that names nothing |
| `knowledge.source_text` (warning) | a `Literature` that a Plan links points at no PDF (`pdf_asset_id` / `pdf_path`), or at one that is not there |
| `experiment.mixed_workflow` (warning) | the runs of one experiment were executed by different workflow versions (by the `workflow_hash` of each run's latest succeeded attempt that recorded one), so the code is one of the differences between them |
| `experiment.adopted_results` (warning) | runs whose latest succeeded attempt was adopted: their results are files molab was handed, not ones it saw made |

### Control flow lives in the links and the fields

There is no class per control structure. The reasoning is read from the typed
links and the class fields:

| Control flow | How knowledge says it |
|---|---|
| condition / judgement | a `Hypothesis` and its `verdict` |
| evidence for or against | a link with role `supports` or `contradicts`, from a `Finding` to a `Hypothesis` |
| pass / cannot tell | `verdict: unsettled` |
| iteration | the document rewritten in place, or a successor written with `replaces` (the old one is deleted, its readers relinked; git keeps it) |
| dependency | `derived_from` (a run that made the bytes, a document revised) |
| mention | `cites` (a source), `references` (anything else) |

The edge roles are `derived_from`, `supports`, `contradicts`, `cites`, and
`references`. `molab init` relabels a link written with a retired role
(`@records`, `@supersedes`) as `@derived_from`. A typed link is written
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
`TypeError`. To point at the document that records a run, `.ref` that
document:

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

`append_link(doc, target, role=…)` is the one edge writer underneath `.ref`.
It also takes a live entity: a project, experiment, run or asset is linked by
its `molab:` ref, a bare path as given. `cite=[(target, role)]` on
`write_knowledge` and `cites` on `POST /api/knowledge/doc` (a list of
`{target, role}`, the target a workspace-relative document path or a `molab:`
ref, the role `cites` when omitted) both go through it. A cite that names
nothing refuses the write (422 over HTTP) and nothing lands.

## Writing into a workspace

One verb writes knowledge into a workspace tree, hosted by a `Folder`:

- `write_knowledge(host, *, name, of, sources, created_by, text, cite=(), title="")`
  — write a document of class `of`, idempotent on `name`.

`Note.mount(host, name, *, body="")` is that verb for a `Note`: a repeat call
never truncates an existing body.

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

## Class fields

A document's fields are validated against its class on every write
(`molab knowledge write --fields JSON`, `fields` on `POST /api/knowledge/doc`,
and the verb below). They can be replaced whole, from the CLI or over HTTP;
both call `replace_fields`:

- `molab knowledge fields DOC` prints `{relPath, cls, fields, digest}` as JSON;
  `GET /api/knowledge/doc/fields?path=…` returns the same.
- `molab knowledge fields DOC --set JSON [--if-match DIGEST]` replaces them
  (`--set` also takes a path to a JSON file; a key it omits is removed), as
  `PATCH /api/knowledge/doc/fields?path=…` does with `{fields, ifMatch, body?}`.
  A stale digest is refused (409 over HTTP), and so is an undeclared key or a
  refused value (422); the CLI exits 1 with the class's message and writes
  nothing. Each replacement is a `knowledge.fields_replaced` history commit.

A reviewer accepts a Note with
`molab knowledge fields knowledges/<slug>.md --set '{"status": "active"}'`.

`POST …/runs/{run}/executions` accepts `requestKey` (idempotency: the same key
returns the attempt already created) and `requestedBy` (the software agent
recorded as the attempt's creator).
