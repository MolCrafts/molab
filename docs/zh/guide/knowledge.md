# 知识与交叉引用

一个 project 的知识不是一堆彼此独立的文档，而是它下面 **experiment 知识的索引**
—— 写在各 experiment 之下的 finding、report、observation 与 note —— 由属于这些
experiment 的 **计划**（`Plan`）与 **总结**（`Report` / `Finding`）粘合起来。工作区
记录算过什么、为什么算；知识记录这些结果*意味着什么*。

没有第二套笔记数据库，也没有中心索引：文件系统就是数据库。一份文档就是一个
markdown 文件，它的路径就是它的身份。

## 文档落在哪里

内置知识落成 `knowledges/` 容器下的 **一个 markdown 文件**。project 的索引与它的
experiment 并列；每个 experiment 的结论落在该 experiment 之下：

```text
lab/projects/polymer-cg/
├── knowledges/tg-index.md                   ← project 对自己 experiment 的索引
└── experiments/solvation-sweep/
    └── knowledges/tg-result.md              ← 某个 experiment 的结论
```

`.md` 是 molab 落盘的形态。`.mdx` 文件在读取时被接受，但落盘永远是 `.md` —— `.mdx`
只在读取一侧被承认。

所有非叙事的内容都在文件的 YAML frontmatter 里，最重要的是标出该文档属于哪个知识
类的 **`class`** 字段：

```yaml
---
class: Finding
tags: [thermal]
---
```

## 构造与定位一份文档

构造要给出一个 **宿主**（host）与一个 **名字**（name）；宿主是 workspace 的
`Folder`，类据此自行推导落点：

```python
from molab.knowledge import Note
from molab.workspace import Workspace

ws = Workspace("./lab", name="Lab")
ws.materialize()
experiment = ws.add_project("polymer-cg").add_experiment("solvation-sweep")

note = Note(experiment, "Analysis Notes")   # 只绑定路径，不碰磁盘
note.write("# Analysis Notes\n\nQuench at 10 K/ns.\n")
```

`Note(experiment, "Analysis Notes").path` 是
`<experiment>/knowledges/analysis-notes.md`，`write` 就是把字节写到那里。绑定名字
时不会碰磁盘，直到第一次 `write` 才落盘。

构造一律使用**具体类**。`Knowledge` 基类是目录形态的概念，用 `Knowledge(host, name)`
构造会落下一个目录，而不是一个 markdown 文件。

**路径只是「怎么找到它」。** 要打开一份已经存在的文档 —— 来自检索、来自 `ls`、来自
另一份文档里的链接 —— 用 `Knowledge.open`，它会从 frontmatter 把类读回来：

```python
from molab.knowledge import Knowledge, Note

doc = Knowledge.open(experiment.resolve() / "knowledges" / "analysis-notes.md")
assert type(doc) is Note                      # `class:` frontmatter 被如实还原
assert doc.read().startswith("# Analysis Notes")
```

`molab.knowledge.location.folder(host, name, of)` 就是这条推导本身 —— `of` 是知识
类，返回值是**落盘路径**：

```python
from molab.knowledge.location import folder

assert Note(experiment, "Analysis Notes").path == folder(experiment, "Analysis Notes", Note)
```

## 六个类

每个类都落成一个 markdown 文件；`class:` frontmatter 标出是哪一个：

| 类 | `class:` frontmatter | 用途 |
|---|---|---|
| `Note` | `class: Note` | 自由笔记 |
| `Literature` | `class: Literature` | 一条文献记录；书目字段在 frontmatter 里，PDF 只记路径，从不拷贝 |
| `Report` | `class: Report` | 成文分析，包括失败 Run 的分析 |
| `Finding` | `class: Finding` | 收获的科学结论 |
| `Plan` | `class: Plan` | 实验或项目的计划书 |
| `Observation` | `class: Observation` | 记录的观察或既定选择 |

`Report`、`Finding`、`Plan`、`Observation` 在构造时至少需要一个 `SourceRef` —— 它们
是有出处的文档；`Note` 与 `Literature` 不需要。

## 交叉引用才是粘合机制

文档的正文就是它的叙事，而正文里的 markdown 链接**就是**知识图。它们由 `.ref`
写下，入参是另一份 **Knowledge** —— 一个文档对象，或定位到它的磁盘路径：

```python
from molab.knowledge import Finding, SourceRef

finding = Finding(experiment, "Tg Result", sources=[SourceRef(kind="run", ref="run-0001")])
finding.write("# Tg Result\n\nTg rose with cooling rate.\n")

note.ref(finding)          # 用对象……
note.ref(finding.path)     # ……或用路径 —— 两种写法写出同一条边
```

`.ref` **绝不**接受 project / experiment / run 的坐标：不是 `Folder`、不是 run id、
不是 params。那些都不是知识，`.ref` 一律以 `TypeError` 拒绝。要指向某个 run 或
experiment，先找到记录它的那份文档，再 `.ref` 那份文档：

```python
run_record = Knowledge.open(experiment.resolve() / "knowledges" / "run-0001.md")
note.ref(run_record)
```

边可以从树上重算 —— 什么都不存两份，也没有单独的 Backlink 类型：

```python
for edge in note.links():
    print(edge.role, edge.target)     # 例如 references …/knowledges/tg-result.md
```

`.cite` 是更松的兄弟：知识目标交给 `.ref`；否则按原样把给出的路径链上。

## 写进工作区

两个模块级动词把知识写进 workspace 树，宿主都是 `Folder`：

- `mount_note(host, name, *, body="")` —— 幂等地挂上一份 `Note`；重复调用绝不截断
  已有的正文。
- `write_knowledge(host, *, name, of, sources, created_by, text, cite=(), title="")`
  —— 写一份有出处的文档，按 `name` 幂等。

`harvest_run` 把一个终态 Run 的结果收获成它 experiment 之下的知识：

```python
from molab.knowledge import Finding, harvest_run

finding = harvest_run(
    run, of=Finding,
    narrative="Tg rose with cooling rate.",
    created_by="lin",
)
```

只有**终态** Run（`succeeded` / `failed` / `cancelled`）才能收获，且 `narrative`
必须非空 —— 收获是解释，不是归档；原始记录已经在 `run.json` 与 Run 的 artifacts 里。
`created_by` 是必填的关键字参数。`of` 通常是 `Finding`、`Observation` 或 `Report`。

## 分层

`molab.knowledge` 依赖 `molab.workspace` —— 一份文档需要一个宿主 folder 才知道自己
落在哪 —— 且这条依赖是单向的：`molab.workspace` 不认识 knowledge。

## 检索组 wiki

知识不必住在工作区里。一个实验室 wiki 就是一个文档目录：把它注册成命名 source，
按关键词检索：

```console
$ molab knowledge init /data/group/wiki --title "Lab notes"
$ molab knowledge sources add lab-wiki /data/group/wiki
$ molab knowledge search "cooling rate for Tg"
$ molab knowledge read lab-wiki:tg-index
```

检索是作用在 title / tags / path / body 上的 **BM25F**，多个 source 的结果用倒数
排名融合（reciprocal rank fusion）合并。中文会切成 unigram 与相邻的 bigram —— 没有
分词器、没有词典、没有 embedding。这是关键词排序，不是 RAG。

在 Python 里，已注册的 source 打开成一个树句柄，其 `walk()` 枚举它的文档，
`search(...)` 对它们排序：

```python
from molab.knowledge.sources import open_source

wiki = open_source("lab-wiki")
for doc in wiki.walk():
    print(type(doc).__name__, doc.path)
for hit in wiki.search("cooling").hits:
    print(hit.entry.title)
```

**已知缺口。** 一个 markdown 文档只有在 `knowledges/` 容器之下才会被遍历 —— 那是
宿主工作区给它的布局。`molab knowledge search` 背后的跨 source 检索
（`search_sources`，建立在 `Bundle` 之上）早于文件文档形态：它只下降目录，看不见
`knowledges/<name>.md` 这样的文件，所以今天由散落 `.md` 组成的 wiki 适合用
`Knowledge.open(path)` 逐份读，而不是靠跨 source 检索。

## 下一步

- 知识所落的工作区，见 [工作区模型](../concept/workspace.md)。
- 记录与资产的具体 Python API，见 [工作区 API](workspace-api.md)。
- 可复用数据与溯源，见 [资产与可复现性](../concept/assets-and-reproducibility.md)。
