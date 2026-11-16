# 工作区模型

工作区层是磁盘上的持久记录。它回答*执行后留下什么*。

## 四层层级

```
工作区 Workspace     ← 根目录（如 ./lab）
└── 项目 Project      ← 分组相关工作（如 qm9）
    └── 实验 Experiment ← 可重复定义（工作流 + 参数）
        └── 运行 Run       ← 一次具体执行尝试
```

| 层级 | 是什么 | 在磁盘上 |
|---|---|---|
| **工作区** | 一组工作的根 | `index.md` |
| **项目** | 分组相关实验 | `projects/<slug>/index.md` |
| **实验** | 一个工作流 + 参数空间 | `projects/<slug>/experiments/<slug>/index.md` |
| **运行** | 一次带状态和输出的执行 | `projects/<slug>/experiments/<slug>/runs/<params>/index.md` |

每一层只保留一个文件：它的 `index.md`。文件开头的 YAML frontmatter 就是这一层的**记录**——molab 写入的字段（`type`、`id`、`name`、……、`schema_version`）；之后的 markdown 是你写的叙述。frontmatter 的 `index:` 键下，molab 还维护一个派生块，指向下一层（带相对 `path` 的 `children` 行、运行的 `executions`、指回上层的 `parent`），因此人或智能体可以从根 `index.md` 出发走遍整棵树，而无需列目录。molab 在每次变更时重写这个块，从不读取它来做任何决定；`molab index sync` 会整体重建它。

## 定义 vs. 结果

关键区别在于**实验**（你打算重复什么）和**运行**（实际发生了什么）。实验携带工作流引用、参数空间和溯源信息。运行是不可变意图（其 `index.md` 中的记录）。每次尝试是 `executions/eNN/` 下的一次 Execution（`execution.json` 持有状态、结果、错误）。

没有这个分离，重试和比较很快变得模糊不清。

## 配置文件与元数据

配置文件（`molcfg.yaml`）位于工作流执行层和工作区持久层之间的边界。任务将配置文件字段作为命名参数读取。解析后的配置文件——名称、合并后的配置、`config_hash`——存储在每次尝试的记录上。你可以事后查看 `executions/eNN/execution.json`，恢复该次尝试所使用的确切配置。

## 磁盘布局

```
workspace_root/
├── index.md                      ← 工作区记录（UUIDv7 `id`）+ `index:` + 叙述
├── knowledges/<name>.md          ← 可选的工作区级知识（一个 markdown 文件）
└── projects/<project-slug>/
    ├── index.md                  ← 项目记录 + `index:` + 叙述
    ├── knowledges/<name>.md      ← Finding / Plan / Note / …
    └── experiments/<experiment-slug>/
        ├── index.md              ← 实验记录 + `index:` + 叙述
        ├── knowledges/<name>.md
        └── runs/<key=value_…>/   ← 目录名就是参数
            ├── index.md          ← 运行记录：只有逻辑定义
            ├── values/           ← 每个任务的输入/输出，按内容只存一份
            └── executions/e01/   ← 一次尝试；`e01` 就是它的 id
                ├── execution.json
                ├── alive         ← 所有者心跳是 mtime
                ├── workflow.json ← 节点日志；按 ref 引用 values/
                ├── artifacts/
                ├── out/<task>/
                └── jobs/
```

没有 children-index 文件。`ls` 就是索引；`index:` 块只是 molab 与之保持同步的便利副本。目录里还留着 `workspace.json` / `project.json` / `experiment.json` / `run.json` / `meta.json`、又没有当前 `index.md` 记录时，读取会拒绝（`UnmigratedLayoutError`）。`molab init` 把这份记录，以及格式不对的 `index:` 块，重写成当前的 `index.md`，并删掉旧的 meta 文件。molab 只读 `index.md`。

内置知识每份文档落成一个 markdown 文件 —— `knowledges/<name>.md`，知识类名写在文件的 `class:` frontmatter 里。`.md` 是落盘形态；`.mdx` 只在读取时被接受。格式归 `molab.knowledge` 所有，它拥有每一份知识文档；工作区只把它当作树里的一个文件，自身从不提及 knowledge。

## 下一步

- 具体的 Python API，见 [工作区 API](../guide/workspace-api.md)。
- 可复用数据和溯源，见 [资产与可复现性](assets-and-reproducibility.md)。
- 发现此层级的 CLI，见 [CLI 与配置文件](../getting-started/cli-and-profiles.md)。
