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

note = Note(experiment, "Analysis Notes")  # 只绑定路径，不碰磁盘
note.write("# Analysis Notes\n\nQuench at 10 K/ns.\n")
```

`Note(experiment, "Analysis Notes").path` 是
`<experiment>/knowledges/analysis-notes.md`，`write` 就是把字节写到那里。绑定名字
时不会碰磁盘，直到第一次 `write` 才落盘。

构造一律使用**具体类**。`Knowledge(host, name)` 会抛出 `TypeError`：基类不是文档，
也不会去构造子类。

**路径就是同一个构造函数。** 已经在磁盘上的文件 —— 来自检索、来自 `ls`、来自另一份
文档里的链接 —— 知道它是笔记就写 `Note(path)`。已经落盘的有出处文档写
`Finding(path)`，不必再传 sources。基类不会读 `class:` 再返回另一种类型。

```python
from molab.knowledge import Note

doc = Note(experiment.resolve() / "knowledges" / "analysis-notes.md")
assert type(doc) is Note
assert doc.read().startswith("# Analysis Notes")
assert Note(experiment, "Analysis Notes").path == doc.path
```

## 文档类

一份文档只属于一个类，一个类只回答一个问题。回答两个问题的文档应当拆成两份。如果一句话
既能归到这个类、又能归到那个类，错的是定义，不是作者。每个类都落成一个文件；`class:`
frontmatter 标出是哪一个：

| 类 | 它回答的唯一问题 | 记录（frontmatter） | 绝不包含 |
|---|---|---|---|
| `Plan` | 我们在问什么，范围多大，受哪些约束？ | 无 | 阶段、工作项、判据、待检验的断言（那些是 Hypothesis） |
| `Hypothesis` | 我们断言什么会成立？ | `verdict`：`open` \| `supported` \| `refuted` \| `unsettled`（默认 `open`） | 证据本身（那是 Finding） |
| `Roadmap` | 工作按什么顺序做？ | `stages` | 工作项、判据、状态 |
| `Todo` | 还剩哪些工作？ | `items` | 阶段、判据 |
| `Milestone` | 一个阶段何时算关闭？ | `stage`、`criterion`、`status`（`open` \| `met` \| `missed`） | 阶段、工作项 |
| `Observation` | 在做任何解释之前，观察到了什么、给定了什么？ | 无 | 选择（Decision）、结论（Finding） |
| `Decision` | 选了什么，谁选的，为什么？ | `status`：`open` \| `made`（默认 `made`） | 观察到的事实、结果 |
| `Finding` | 证据确立了什么？ | 无 | 选择、计划 |
| `Report` | 我们要告诉读者什么？它只做汇编，不提出新的断言。 | 无 | 别处没有陈述过的结果 |
| `Literature` | 一份已发表的文献说了什么？ | 书目字段；PDF 只记路径，从不拷贝 | |
| `Delegation` | 哪项受监督的工作正在进行？（操作性的） | 委托记录：作用域、目标、授权动作、预算与消耗、验收与停止条件、等待、worker 尝试 | |
| `Note` | 以上都不是：对推理不作任何断言的自由文本。 | 无 | |

长期有效的选择是 `Decision`，不是 `Observation`。`Report` 由它的目的（告诉读者）界定，
而不是由篇幅界定：一个结果写得再长，也仍然是 `Finding`。

`verdict` 或 `status` 的取值超出词表时，写入会被拒绝，`molab validate` 也会报告
（`knowledge.record`）；它绝不会被默认值悄悄替换。

除 `Note` 与 `Literature` 之外，每个类在构造时都至少需要一个 `SourceRef` —— 它们是有出处
的文档。

Plan、Roadmap、Todo、Milestone 是一次战役的四份文档，各自只做一件事。Plan 不列阶段。Roadmap 不列工作项。Todo 不定义阶段顺序。Milestone 不列具体工作。后三份引用 Plan。`campaign_of(plan)` 读回这一组；`check_campaign` 检查每条 todo 和 milestone 点名的阶段确实在路线图上。

### 控制流在链接和记录里

没有哪个类是为某种控制结构单独设的。推理过程从带类型的链接和记录字段里读出来：

| 控制流 | 知识怎么表达 |
|---|---|
| 条件 / 判断 | 一份 `Hypothesis` 和它的 `verdict` |
| 支持或反对的证据 | 从 `Finding` 指向 `Hypothesis`、角色为 `supports` 或 `contradicts` 的链接 |
| 通过 / 无法判断 | `verdict: unsettled` |
| 迭代 | 一份新文档，用 `supersedes` 取代它所修订的那份 |
| 决策点 | 一份 `Decision`；`status: open` 表示它在等人来定 |
| 依赖 | `derived_from` |
| 提及 | `cites`（文献来源）、`references`（其他任何对象）、`records` |

边的角色有 `derived_from`、`supersedes`、`supports`、`contradicts`、`cites`、`records`
和 `references`。带类型的链接写作 `- [@supports label](target)`；不带角色的链接就是
`references`。这些角色只是一套词表：molab 不检查 `supports` 或 `contradicts` 链接连接的
是哪两个类。

## 交叉引用才是粘合机制

文档的正文就是它的叙事，而正文里的 markdown 链接**就是**知识图。它们由 `.ref`
写下，入参是另一份 **Knowledge** —— 一个文档对象，或定位到它的磁盘路径：

```python
from molab.knowledge import Finding, SourceRef

finding = Finding(experiment, "Tg Result", sources=[SourceRef(kind="run", ref="run-0001")])
finding.write("# Tg Result\n\nTg rose with cooling rate.\n")

note.ref(finding)  # 用对象……
note.ref(finding.path)  # ……或用路径 —— 两种写法写出同一条边
```

`.ref` **绝不**接受 project / experiment / run 的坐标：不是 `Folder`、不是 run id、
不是 params。那些都不是知识，`.ref` 一律以 `TypeError` 拒绝。要指向某个 run 或
experiment，先找到记录它的那份文档，再 `.ref` 那份文档：

```python
run_record = Note(experiment.resolve() / "knowledges" / "run-0001.md")
note.ref(run_record)
```

边可以从树上重算 —— 什么都不存两份，也没有单独的 Backlink 类型：

```python
for edge in note.links():
    print(edge.role, edge.target)  # 例如 references …/knowledges/tg-result.md
```

`.cite` 是更松的兄弟：知识目标交给 `.ref`；否则按原样把给出的路径链上。

## 写进工作区

两个模块级动词把知识写进 workspace 树，宿主都是 `Folder`：

- `mount_note(host, name, *, body="")` —— 幂等地挂上一份 `Note`；重复调用绝不截断
  已有的正文。
- `write_knowledge(host, *, name, of, sources, created_by, text, cite=(), title="")`
  —— 写一份有出处的文档，按 `name` 幂等。

`Finding.harvest`（`Observation`、`Report` 上是同一个方法）把一个终态 Run 的结果
收获成它 experiment 之下的知识：

```python
from molab.knowledge import Finding

finding = Finding.harvest(
    run,
    narrative="Tg rose with cooling rate.",
    created_by="lin",
)
```

只有**终态** Run（`succeeded` / `failed` / `cancelled` / `interrupted`）才能收获，
且 `narrative` 必须非空 —— 收获是解释，不是归档。原始记录已经在 Run 的 `index.md`
和它登记的 asset 里。`created_by` 是必填的关键字参数。

正文的散文就是这段解释。写出时会为每条出处追加一行链接，不复制状态、参数、错误或结果值。
收获引用最近一次 attempt 登记的每个 asset（`molab:asset/<id>`）。
`results` 里的值若能在这些文件里对上唯一一个点，出处的 span 就是这个点
（JSON 字段 `/loss`，或序列 `loss@10000`）。没有登记 asset、对不上、或对上不止一个点，
都会拒绝，并且什么都不写。下一次运行的 `inputs` 就是文档的 `inputs`。
`read_cited` 读取 span 上的值，`read` 返回正文。工作流不导入知识。

```python
follow = experiment.add_run(inputs=finding.inputs)
finding.read_cited("/loss")  # 0.08，span 上的值
```

`GeneratedParts(run).list()` 只列出某次 attempt 登记的图片 asset（媒体类型
`image/*`，或带 `part` 标签）。它不写第二份文档。叙事要用这张图时，在收获里引用
那个 asset。

```console
$ molab knowledge parts <run-id> --path .
```

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
from molab.knowledge.sources import KnowledgeSourceStore

wiki = KnowledgeSourceStore().open("lab-wiki")
for doc in wiki.walk():
    print(type(doc).__name__, doc.path)
for hit in wiki.search("cooling").hits:
    print(hit.entry.title)
```

`qualify_run_id` 永久保留，用来把遗留的裸 run id 限定成引用。不是工作区的 source，其注册根本身就是容器。如果某个 wiki 的文档放在
`<wiki>/knowledges/` 下，要把该目录重新注册为 source 根：
`molab knowledge sources remove <name>`，然后
`molab knowledge sources add <name> <wiki>/knowledges`。

## 当前文档

知识文档是 `<host>/knowledges/<slug>.md`。旧的目录形态和 `references/` 布局不再导入。

## 下一步

- 知识所落的工作区，见 [工作区模型](../concept/workspace.md)。
- 记录与资产的具体 Python API，见 [工作区 API](workspace-api.md)。
- 可复用数据与溯源，见 [资产与可复现性](../concept/assets-and-reproducibility.md)。
