# 知识

工作区不只记录计算产出了什么，也记录为什么跑、结论是什么、依据哪些文献。知识就是目录树：路径即身份，类名 json 是头，`index.md` 是叙事。没有第二套笔记数据库，文件系统就是数据库。

## 心智模型

按路径构造文档：

```python
from molab.knowledge import Note

note = Note("/data/group/wiki/cooling-rate")
note.write("# Cooling rate\n\nQuench at 10 K/ns.\n")
```

磁盘上是 `note.json` + `index.md`。知识目录没有 `meta.json`，头里也没有 `type` / `kind`。读回用 `Knowledge.open(path)`，由文件名还原子类。

`Knowledge` 的六个子类：

| 类 | 头文件 | 用途 |
|---|---|---|
| `Note` | `note.json` | 自由笔记 |
| `Literature` | `literature.json` | 文献；书目字段在头里；PDF 只记路径，从不拷贝 |
| `Report` | `report.json` | 成文分析，包括失败 Run 的分析 |
| `Finding` | `finding.json` | 收获的科学结论 |
| `Plan` | `plan.json` | 实验 / 项目计划书 |
| `Observation` | `observation.json` | 观察或既定选择 |

打开任意目录树的方式相同——组 wiki、git 仓库、工作区：

```python
from molab.knowledge import Knowledge, Note

tree = Knowledge("/data/group/wiki")
for item in tree.walk():
    print(type(item).__name__, item.path)
for hit in tree.search("cooling", of=Note).hits:
    print(hit.entry.title)
```

`index.md` 里的 Markdown 链接**就是**知识图。六个类都用 `cite` 写下这条边：`finding.cite(literature)`。谁引用了某篇，从树上的 `links()` 重算，没有单独的 Backlink 类型。

## 写到实验下

工作区通过 `write_knowledge` / `add_knowledge` 把文档挂在 `<host>/knowledges/<slug>/`。身份仍是路径；Folder 父级只决定目录。

```python
from molab.knowledge import Note
from molab.workspace import Workspace

ws = Workspace("./lab", name="Lab")
ws.materialize()
exp = ws.add_project("polymer-cg").add_experiment("solvation-sweep")
note = exp.add_knowledge("analysis-notes", Note, "# Analysis Notes\n")
```

```text
lab/projects/polymer-cg/experiments/solvation-sweep/knowledges/analysis-notes/
├── note.json
└── index.md
```

## 文献

```python
from molab.knowledge import Literature, ReferenceMeta

lit = Literature(exp.resolve() / "knowledges" / "frenkel-smit-2002")
lit.write(
    "Frenkel & Smit, *Understanding Molecular Simulation* (2002).\n",
    ReferenceMeta(
        title="Understanding Molecular Simulation",
        authors=("Daan Frenkel", "Berend Smit"),
        year=2002,
        pdf_path="/home/me/Zotero/storage/ABCD1234/frenkel-smit.pdf",
    ),
)
```

`molab knowledge import-zotero` 从本地 Zotero 库写成同样的 `Literature` 目录（只读；PDF 只记路径）。

## 收获与失败分析

对终态 Run 的收获写成 `Finding`（或 `Observation` / `Report`）。Plan 和 Note 是产品类，但不是收获目标。

```console
$ molab runs harvest PROJECT EXP RUN "Tg rose with cooling rate." --of Finding
$ molab runs analyze-failure PROJECT EXP RUN
OK Report: failure-analysis-<run-id>
```

## 搜组 wiki

```console
$ molab knowledge init /data/group/wiki --title "Lab notes"
$ molab knowledge sources add lab-wiki /data/group/wiki
$ molab knowledge search "cooling rate for Tg"
$ molab knowledge read lab-wiki:lab-notes
```

`Knowledge(root).search` 是对 title/path/body 的 BM25F。中文同时切 unigram 和相邻 bigram，没有分词器。这不是 RAG。
