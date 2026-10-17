---
title: Molab 前端与 Dashboard 重设计规范
description: Molab Web 前端的产品定位、信息架构、功能边界、Dashboard 目标形态与分阶段整改要求。
---

# Molab 前端与 Dashboard 重设计规范

| 字段 | 值 |
| --- | --- |
| 状态 | Implemented |
| 范围 | `apps/web` 产品体验、信息架构与前端架构 |
| 主要决策 | 推翻当前 Runs Overview 式 Dashboard，建立 workspace operational home |
| 日期 | 2026-08-31 |

## 1. 摘要

Molab 的 Web UI 应当是计算科学家和研究工程师的实验操作台，而不是展示系统能力的通用指标看板。

当前界面最主要的问题不是视觉样式，而是信息架构：Runs Overview 同时承担状态汇总、运行分析、活动流、时间线和 Dashboard 布局管理等职责；顶级导航又同时暴露 Project、Run、Activity、Workflow、Workspace、Asset、Agent 和 Knowledge 等不同抽象层级的对象。用户需要先理解系统内部模块划分，才能决定下一步去哪里。

本规范要求：

- 新建真正的 workspace Dashboard，负责 operational triage 和继续工作。
- Runs 页面回归运行 inventory，默认显示可筛选列表。
- Workflow 归入 Experiment，不再作为一级导航。
- Activity 暂时移除；只有建立真实跨实体事件模型后，才可作为 Audit 二级页面返回。
- 删除 Dashboard panel manager、重复状态卡、默认 Gantt 和无行动价值的分析模块。
- 右侧面板只检查当前实体，不再永久混入 Copilot。
- 统一 server state、数据完整性和 feature contribution 边界，使功能可以独立增加和移除。

这是一项信息架构重设计，不应作为当前 Dashboard 的增量美化处理。

### 1.1 当前实施进度

截至 2026-08-31，P0–P4 的规划实现已经落地：

- `/` 已成为 workspace Dashboard。
- Dashboard 使用 Attention、Active runs、Continue work，不再使用 card canvas。
- `/runs` 已移除 Overview，默认进入 List，只保留 List 与 Timeline。
- Activity 与 Workflows 已从一级 rail 移除；旧路由暂时保留以兼容现有入口。
- Dashboard 使用 rail-only shell，不显示无职责的 explorer。
- Right Inspector 不再永久挂载 Copilot。
- 顶栏局部搜索已明确为 `Filter explorer`，Dashboard 不显示无效 filter。
- 通用 `ContentSection` 与 `PageHeader` 已进入 `molcrafts-ui` registry，并以同源文件接入 Molab。
- Experiment 的 Overview、Workflow、Runs、Compare 已成为 route-backed tabs；Workflow 的规范路径为
  `/projects/:projectId/experiments/:experimentId/workflow`。
- Experiment Overview 只保留 Workflow 摘要与入口；完整 graph 和 expand modal 已删除，Workflow tab 是唯一主要 graph surface。
- 内部 Workflow selection 与旧 `/workflows/:id` 链接会归并到所属 Experiment Workflow tab。
- Project Overview 已区分 server-reported total 与 lazy client snapshot；只有 runs 完整加载时才显示状态分布和成功率。
- Project Experiment 列表不再把未加载的 runs 显示成 `No runs`。
- Project 的 Overview、Experiments、Assets、Settings 已成为 route-backed tabs；Runs 的 List/Timeline 继续使用既有 URL query state。
- 已删除断开渲染树的 Dashboard panel/layout、KPI strip/card、Activity chart、aggregate row 和专用 Sparkline，并移除其孤立派生计算。
- 通用 `ExplorerShell`（icon rail + explorer column）已进入 `molcrafts-ui` registry；Molab 使用同源文件，领域 explorer 内容仍留在产品内。
- Dashboard Attention 已接入权威 pending approvals，并按可行动优先级与更新时间排序；每项提供 `Review`、`Inspect`、`Open settings` 或正确数据源的 `Retry`。
- Attention 首屏最多显示 5 项；只有被折叠事项共享同一目标页面时才显示可点击 overflow，避免伪造一个不存在的统一 `View all` 页面。
- Continue work 已覆盖 Agent task/session，不再只展示 Project、Experiment 与 Run。
- pending approvals 已迁入统一 React Query server-state：Dashboard、全局 bell、task inbox 与 plan decision bar 共享缓存和 invalidation，只有全局 bell 持有 SSE 连接。
- approval 的 query、command、presentation、review surface、shell bell 与测试已收拢到 `app/approvals`；Agent 和 Dashboard 只消费 feature API。
- 顶级 section 的 route、label、placement、shell mode、path matcher 与 selection retention 已集中到 `app/navigation/sections.tsx`；navigation state、breadcrumb 与 rail 不再各自维护重复 map/switch。
- `NavigationRail` 与 `NavigationExplorerHost` 已从原 1600 行 `LeftPanel` 中拆出；`LeftPanel` 现为 69 行纯 adapter，共享 chrome 继续由 `molcrafts-ui` 的 `ExplorerShell` 提供。
- Projects、Runs、Agent、Knowledge、Assets 与 Files 已成为 feature-owned full explorer surfaces；各自拥有 tree/facets、header actions、permissions、commands、dialogs 和 tests，并通过 lazy contribution 挂载。
- legacy Activity 与 Workflows explorer 也已封装为 hidden compatibility contributions，旧 URL 可用但不会返回一级 rail 或重新污染 `LeftPanel`。
- Files、Agent 与 Projects 的 destructive/create actions 已在 feature 内统一 permission gate；shell 不再持有领域 CRUD 或提前订阅 Runs query。
- Settings 使用 rail-only full-surface shell；Files 的 rail、explorer 与 breadcrumb 文案已统一，Assets/Files 通过 shared rail separator 与 primary workflow 分组。
- `molcrafts-ui` 的 `LeftIconRailItem` 已增加通用 `separatorBefore` 能力，registry 已重新构建；Molab vendored source 与 registry source 保持一致。
- Dashboard、Runs、Settings 及 legacy compatibility 页面的 landing surface 已作为 lazy navigation contribution 挂载；`CenterPanel` 不再 import 页面或按 section id 分支。
- Runs 现在由 feature 自己注册 contextual inspector surface；`AppShell` 只管理通用 surface 的 identity、显隐与布局，不再 import `RunInspector` 或理解 Runs 数据结构。
- Center 与 Right panel 已共用 renderer slot resolver；`RightPanel` 只负责当前 entity renderer 与 lineage，不包含 feature-specific inspector branching。
- Lazy contribution 统一由 `LazySurface` 隔离 loading/error/retry；加载失败不再伪装成 empty，也不会击穿整个 shell。
- Renderer contract 已从完整 `WorkspaceSnapshot` 收窄为 `RendererSnapshot`，具体 Project/Experiment/Run renderer 使用编译期 `ScopedRendererProps` 声明字段范围。
- Knowledge list/note/backlinks 使用同一 TanStack Query key/cache；command palette 只在首次打开 Go to 时启用 Knowledge inventory query。
- Bootstrap 独立 slices 已并行；Assets、Logs、Gantt、metrics、preview 和重型 plugin surface 均按 owner/surface 按需加载。
- Internal plugin 已改为轻量 descriptor + lazy loader；可选 plugin 在 first render 后加载，重型实现只在 contribution 实际渲染时下载。
- Workspace Runs API 已支持 offset/limit，并在分页前提供真实 total/aggregate；前端 2000 rows pipeline p95 约 2 ms，暂不引入 virtualization。
- Canonical Project/Experiment/Run deep link 会按 URL 层级补载 lazy entity chain，不再把未加载数据误显示为 not found。
- 页面标题由 `PageHeader` 单点拥有，breadcrumb 只显示可导航 ancestors；landing surface 不再重复渲染空 breadcrumb header。
- 通用 `WorkbenchOperationState` 与增强后的 `EmptyState` 已进入 `molcrafts-ui` registry，Molab vendored source 与 registry source 可机械比对。
- request count、React Profiler、bundle 和 Runs 数据规模基线已落盘到 `frontend-performance-baseline.md`。

最终校验命令和结果记录在本规范的完成定义下方；`molcrafts-ui` registry 当前包含 39 items。

不阻塞本轮完成、但需要产品/telemetry 决定的后续项：

- 在兼容窗口结束后评估移除仍有调用方的 legacy Activity 与 Workflows collection route。
- `/api/workspace/runs` 的 server aggregate 仍需全量扫描；只有生产 telemetry 证明后端扫描成为瓶颈时再引入索引或预计算。
- 超过 2000 rows 或浏览器 paint/scroll 出现可复现瓶颈后，再评估 virtualization。

## 2. 背景与问题

### 2.1 产品事实

Molab 的核心对象层级是：

```text
Workspace
└── Project
    └── Experiment
        └── Run
            └── Execution
```

产品核心任务是：

1. 设计和配置实验工作流。
2. 启动、恢复、重跑或取消 Run。
3. 监控 Execution，查看日志、状态和输出。
4. 诊断失败并比较实验结果。
5. 将结果整理为 Assets 和 Knowledge。

### 2.2 当前 Dashboard 的结构性问题

当前 `/runs` Overview 实际承担了 Dashboard 职责，并默认展示：

- Running、Pending、Failed、Succeeded、Avg wait KPI。
- Status mix。
- Backends & failures。
- 24 小时 Activity chart。
- Workspace activity feed。
- Gantt。
- Panel hide、reorder、resize 和 reset。

这导致：

- 同一个 status 在左侧 facets、KPI 和 Status mix 中重复出现。
- Analytics、navigation、status、activity 和 workspace control 处于同一层级。
- 所有 panel 使用相似视觉容器，缺少明确优先级。
- 页面没有一个清晰的 primary action。
- 用户需要管理 Dashboard 布局，而不是直接处理科研任务。
- Timeline 中已经存在的 Gantt 又在 Overview 中重复出现。
- 零数据或低价值图表仍然长期占据空间。

### 2.3 顶级导航问题

当前一级入口混合了：

- 领域层级：Projects、Runs。
- 实验配置：Workflows。
- 横切视图：Activity。
- 基础设施：Workspace、Assets、Settings。
- 独立工作区：Agent、Knowledge。

这些入口的抽象层级、使用频率和用户目标并不一致，不应全部获得同等导航权重。

## 3. 产品定位

### 3.1 核心用户

- 运行计算实验的 computational scientists。
- 构建、维护和诊断科研工作流的 research engineers。
- 同时管理多个 Project、Experiment 和长时间运行任务的高级用户。

本阶段不以管理层、只读报表用户或通用 BI 用户为主要设计对象。

### 3.2 用户打开 Molab 时的首要问题

按优先级排序：

1. 当前是否有失败、阻塞、审批或连接异常需要处理？
2. 哪些实验正在运行或等待运行？
3. 如何继续上一次工作？
4. 在当前 Project/Experiment 上下文中，下一步动作是什么？
5. 在需要时，如何进入 Logs、Timeline、Outputs、Compare 或 Workflow？

### 3.3 Dashboard 的职责

Dashboard MUST 在 3–5 秒内回答：

- Workspace 当前是否健康？
- 什么需要用户处理？
- 什么正在运行？
- 用户下一步可以进入哪里？

Dashboard MUST NOT 成为：

- 通用 analytics 页面。
- Workflow editor。
- Run detail 或 log viewer。
- Asset/file browser。
- Compute target、plugin 或 access management 页面。
- 系统能力陈列页。
- 可自由拼装的 card canvas。

## 4. 目标与非目标

### 4.1 目标

- 在首屏建立唯一明确的信息优先级。
- 默认展示可操作状态，而不是所有可获得数据。
- 一个 surface 只承担一个主要职责。
- 将 Workflow、Timeline、Logs、Outputs 和管理功能放回正确上下文。
- 消除重复状态、重复入口和重复数据请求。
- 明确 server state、local UI state 和数据完整性的边界。
- 新 feature 能够独立开发、渲染、测试和删除。
- 性能优化以可证明的重复工作和测量结果为依据。

### 4.2 非目标

- 本阶段不进行品牌重塑或整体视觉换肤。
- 不增加新的 analytics 图表。
- 不保留 Dashboard 自定义布局作为产品卖点。
- 不重写全部前端或更换 React、Router、Query 技术栈。
- 不在缺少数据规模和 profiler 证据时全面引入 virtualization 或 memoization。
- 不改变后端领域层级 `Project → Experiment → Run → Execution`。

## 5. 设计原则与不变量

以下规则属于实现验收条件，而不是视觉建议：

1. 一个页面 MUST 有且只有一个主要职责。
2. 同一个指标 MUST NOT 在同一页面以多个同等级组件重复出现。
3. 默认页面 MUST 优先展示可行动信息。
4. Contextual UI MUST 只在相关状态或用户请求后出现。
5. 每个页面 SHOULD 只有一个视觉上的 primary action。
6. 空的 Attention、Analytics 或 Activity 容器 MUST 不渲染，除非它承担 onboarding 职责。
7. 不完整或 lazy-loaded 数据 MUST NOT 伪装为完整 aggregate。
8. 写操作 MUST 明确表达副作用；不得将创建或更新行为描述为 read-only advisory。
9. Feature MUST 尽量通过 manifest、route 和 scoped queries 接入，而不是修改多个中央 switch。
10. 删除一个 feature 时，不应要求理解和修改无关 feature 的内部实现。

## 6. 目标信息架构

```text
Molab
├── Dashboard
│   ├── Attention
│   ├── Active runs
│   ├── Continue work
│   └── Contextual primary action / onboarding
│
├── Projects
│   └── Project
│       └── Experiment
│           ├── Overview
│           ├── Workflow
│           ├── Runs
│           └── Compare
│
├── Runs
│   ├── List
│   └── Timeline
│
├── Agent
└── Knowledge

Secondary / More
├── Assets
├── Files
└── Settings
    ├── Workspaces
    ├── Compute targets
    ├── Plugins
    └── Access
```

### 6.1 一级页面职责

| 页面 | 单一职责 | 默认包含 | 明确排除 |
| --- | --- | --- | --- |
| Dashboard | Workspace operational triage | Attention、active runs、recent work、contextual action | 历史图表、Gantt、文件树、编辑器 |
| Projects | 浏览和进入 Project/Experiment | 层级、搜索、创建入口 | 全局运行分析 |
| Runs | 查找和监控 Run | List、facets、saved filters、inspector | Dashboard KPI 集合 |
| Agent | 查看和处理 Agent task/session | 任务、审批、计划、执行状态 | 通用实体 metadata |
| Knowledge | 搜索、阅读和整理知识 | Tree/search、document detail、backlinks | Run operational status |
| Assets | 跨项目查找产物 | Asset inventory、provenance filter | Run outputs 的重复完整视图 |
| Files | 高级原始文件浏览 | Workspace file tree、preview/editor | Workspace 管理 |
| Settings | 管理系统配置 | Workspace、target、plugin、access | 实体浏览和运行监控 |

### 6.2 路由要求

推荐目标路由语义：

```text
/                         Dashboard
/projects                 Project inventory
/projects/:projectId      Project workspace
/experiments/:id          Experiment overview
/experiments/:id/workflow Experiment workflow
/experiments/:id/runs     Experiment-scoped runs
/experiments/:id/compare  Experiment comparison
/runs                     Run list
/runs/timeline            On-demand timeline
/runs/:runId              Run detail
/agent                    Agent workspace
/knowledge                Knowledge workspace
/assets                   Secondary asset inventory
/files                    Advanced file workspace
/settings/*               Full-surface management
```

最终 URL 可以适配现有 router 约束，但页面职责和层级 MUST 保持一致。

## 7. Dashboard 功能规范

### 7.1 页面结构

Dashboard SHOULD 使用普通 section 和紧凑列表，而不是一组同权 cards：

```text
Dashboard
├── Attention        conditional; non-empty only
├── Active runs      primary operational list
├── Continue work    3–5 recent entities
└── Empty/onboarding conditional replacement
```

### 7.2 Attention

Attention MUST 只包含用户可以采取行动的异常或阻塞：

- Failed run。
- Blocked run/task。
- Pending approval。
- Unreachable compute target。
- Workspace sync/load error。
- 数据被截断或不完整且会影响当前判断。

规则：

- 没有 attention item 时，整个 section MUST 不渲染。
- Item SHOULD 按 severity、是否阻塞和更新时间排序。
- 首屏 SHOULD 最多展示 5 项，并提供 `View all`。
- 每一项 MUST 提供明确动作，例如 `Inspect run`、`Review approval`、`Reconnect target` 或 `Retry`。
- 不可行动的普通信息 MUST NOT 使用 attention 样式。

### 7.3 Active runs

Active runs 是 Dashboard 的主要稳定内容。

默认范围：

- `running`
- `pending`
- 明确处于恢复、取消或调度过渡状态的 Run

建议列：

- Run name/id。
- Experiment。
- Status。
- Elapsed 或 queued duration。
- Target/backend。
- Last update。

规则：

- 默认最多展示 10 项。
- 整行可进入 Run detail。
- 不再另外展示同一组 status KPI 和 status mix。
- 无 active run 时不显示空表；由 Continue work 或 onboarding 接管页面。

### 7.4 Continue work

Continue work SHOULD 展示 3–5 个最近访问或最近更新的：

- Project。
- Experiment。
- Run。
- Agent task/session。

每项只需要类型、名称、状态/上下文和更新时间。不得将其扩展成完整 Activity feed。

### 7.5 Primary action

Dashboard 的 primary action MUST 根据 workspace 状态决定：

| 条件 | Primary action |
| --- | --- |
| 没有 Project | `Create project` |
| 当前 Project 没有 Experiment | `Create experiment` |
| Experiment 已完成配置 | `Start run` |
| 存在高优先级失败 | `Inspect failed run` |
| 存在 active run | `Open active run` |
| 无异常且存在 recent work | `Continue <item>` |

`New run` MUST NOT 在缺少 Experiment 上下文时作为永久全局 primary action。

### 7.6 Dashboard 明确禁止项

以下内容 MUST 从默认 Dashboard 移除：

- KPI strip。
- Status mix。
- Backend distribution/load chart。
- 默认 24h Activity chart。
- Run-derived Workspace activity feed。
- Gantt。
- Dashboard panel manager。
- Drag、resize、hide、reset layout。
- 永久显示的 Copilot panel。

## 8. 当前功能迁移决策

| 当前功能 | 当前问题 | 目标归属 | 决策 |
| --- | --- | --- | --- |
| Runs KPI strip | 与 facets/status mix 重复 | Active runs | 删除 |
| Status mix | 不产生额外行动价值 | Runs filters 或 compact summary | Dashboard 删除 |
| Backends & failures | 混合资源分布与失败诊断 | Runs analytics / Compute management | 拆分并降级 |
| 24h Activity | 空数据仍占空间 | 后续 Analytics | 当前删除 |
| Workspace activity feed | 实际主要是 Run feed | Audit 或删除 | 当前删除 |
| Overview Gantt | 与 Timeline 重复 | Runs Timeline | 移动 |
| Dashboard layout manager | 将 IA 决策转嫁给用户 | 无 | 删除 |
| 顶级 Activity | 与 feed 重叠，缺少事件模型 | Future Audit under More | 删除 |
| 顶级 Workflows | 与 Experiment 内 workflow 重叠 | Experiment Workflow | 合并 |
| Workspace explorer | 名称与 workspace domain 混淆 | Files | 重命名、降级 |
| Global Assets | 与 scoped Outputs/Assets 重叠 | Secondary Assets | 降级；保留跨项目检索 |
| Right-panel Copilot | 与 Inspector 责任冲突 | Agent / Dashboard attention | 移动 |
| Settings explorer | 外层和内层导航嵌套 | Full-surface Settings | 重构布局 |

## 9. 关键用户工作流

### 9.1 首次使用

```text
Open Molab
→ Dashboard empty/onboarding state
→ Create project
→ Create experiment
→ Configure workflow
→ Start run
→ Open run detail
```

Empty state MUST 包含可执行 action，不能只提示用户“创建一个对象”。

### 9.2 日常返回

```text
Open Molab
→ Review Attention
→ Open active or failed run
→ Inspect execution/logs
→ Take contextual lifecycle action
```

### 9.3 编辑 Workflow

```text
Projects
→ Project
→ Experiment
→ Workflow
→ Edit/validate
→ Return to Experiment Runs or Start run
```

Workflow editor MUST NOT 同时以顶级 workspace、Overview 内完整 graph 和 expand modal 三种主要形态存在。

### 9.4 查找历史 Run

```text
Runs
→ Filter/search list
→ Select row
→ Inspect summary
→ Open detail if needed
→ Open Timeline only when temporal diagnosis is needed
```

### 9.5 系统管理

```text
Settings
→ Workspaces / Compute targets / Plugins / Access
```

Settings MUST 使用专属布局，不保留无关的实体 explorer。

## 10. UI/UX 要求

### 10.1 Visual hierarchy

- 第一屏 MUST 优先显示 Attention 或 Active runs。
- 页面标题 MUST 只出现一次；breadcrumb、explorer heading 和 entity title 不得重复表达相同信息。
- Primary、secondary、tertiary 信息必须通过位置、字号、间距和控件样式明显区分。
- Border 和 background 不得成为所有内容的默认分组手段。

### 10.2 Actions

- 每个 surface SHOULD 只有一个高强调 primary action。
- Refresh、layout、more menu 等 meta action MUST 使用较低视觉权重。
- Lifecycle actions 只在对象和状态允许时出现。
- 复杂 Experiment setup 不应塞入大型 modal；应使用专属 page、drawer 或分步 workspace。

### 10.3 Progressive disclosure

默认展示：

- Attention。
- Active state。
- Recent/continue items。
- 必要的同步和错误信息。

按需展示：

- Timeline/Gantt。
- Historical analytics。
- Backend breakdown。
- Logs 和 Outputs。
- Relationship graph。
- Advanced metadata。

### 10.4 Component patterns

- 优先使用 section、list、table 和 inline status。
- 避免 card soup、nested cards 和无意义 border。
- Badge 只表达有限枚举状态，不作为普通 metadata 容器。
- Icon 必须辅助语义，不能替代不熟悉领域概念的文本标签。
- 同一种选择、确认、详情和 overflow 行为必须使用一致 pattern。

### 10.5 Copy

- 顶栏全局入口使用 `Go to…`，局部列表使用 `Filter…`。
- 使用 sentence case：`New experiment`、`Create experiment`、`Start run`。
- 文案范围必须与数据范围一致；仅统计 Run 的模块不得称为 `Workspace activity`。
- 如果 backend 统计包含所有状态，不得称为 `Backend load`。
- 写操作必须使用明确动词，并在必要时说明会创建 Knowledge、Run 或其他持久对象。

## 11. 前端架构规范

### 11.1 Feature 边界

推荐逐步形成以下职责边界；不要求一次性移动所有文件：

```text
app/
├── shell/
│   ├── navigation/
│   ├── explorer-host/
│   └── inspector-host/
├── features/
│   ├── dashboard/
│   ├── projects/
│   ├── experiments/
│   ├── runs/
│   ├── agent/
│   ├── knowledge/
│   ├── assets/
│   ├── files/
│   └── settings/
├── entities/
├── shared/
└── plugins/
```

Feature SHOULD 自己拥有：

- Routes 或 route contribution。
- Queries 和 commands。
- 页面与 feature-specific components。
- Loading/error/empty states。
- Tests。
- 可选 navigation/explorer/inspector contribution。

### 11.2 Navigation manifest

顶级导航 MUST 从中央 closed-set switch 迁移到 manifest/contribution：

```ts
interface NavigationContribution {
  id: string;
  label: string;
  icon: ReactNode;
  route: string;
  priority: "primary" | "secondary" | "management";
  explorer?: React.ComponentType;
  isAvailable?: () => boolean;
}
```

Shell MUST 只负责排序、选中、渲染和 responsive 行为，不包含 feature CRUD 或 domain branching。

当前实现已用 `app/navigation/sections.tsx` 作为 metadata manifest，并由
`NavigationRail`、`NavigationExplorerHost`、navigation state 和 breadcrumb 共同消费。
所有 primary/secondary explorer 以及 legacy compatibility explorer 已通过 lazy contribution 接入；
Center landing、entity renderer 和 contextual inspector 也通过各自 contribution/registry 接入，shell 只负责解析和隔离渲染。

### 11.3 State ownership

Server state：

- Workspaces、Projects、Experiments、Runs、Executions。
- Assets、Knowledge、Agent tasks。
- Logs、aggregates、target status。

这些数据 MUST 通过统一 query layer 管理缓存、dedup、retry 和 invalidation。

Client/UI state：

- 当前 selection/route。
- Drawer、dialog、popover 开关。
- 未提交表单和 editor draft。
- 临时列宽、排序等局部展示偏好。

Dashboard layout customization 不再属于需要持久化的 client state。

### 11.4 数据完整性

- Lazy tree snapshot 只能用于已加载节点的 navigation。
- Project/Workspace aggregate MUST 使用专属 aggregate/list endpoint，或明确标记 partial/truncated。
- API/query result SHOULD 包含 completeness metadata。
- Lazy load 失败不得伪装为空集合。
- 全局 Activity、Dashboard count 和 Project summary 不得从未知完整性的 snapshot 推导。

### 11.5 Renderer contract

Renderer SHOULD 接收 entity id 和窄范围 view model，而不是完整 `WorkspaceSnapshot` 与通用 callback 集合。

推荐模式：

```ts
useProject(projectId)
useProjectSummary(projectId)
useProjectCommands(projectId)
```

这使数据依赖可检查、更新范围可控，并降低 feature test fixture 成本。

### 11.6 Inspector contract

Right inspector MUST 只展示当前 selection 的：

- Metadata。
- Status。
- Provenance/relations。
- 与当前实体直接相关的 contextual action。

全局 Copilot、Dashboard summary 和跨实体 activity MUST NOT 永久挂载在 Inspector 中。

### 11.7 Plugin contract

- Plugin registry SHOULD 静态注册轻量 descriptor。
- 重型实现 SHOULD 使用 dynamic import。
- Disabled plugin SHOULD 尽可能不进入启动执行路径。
- Plugin contribution 必须能够独立 enable/disable，并具有 isolation test。

### 11.8 Shared UI ownership

跨 Molcrafts 产品通用、无 Molab 领域语义的 UI MUST 以
`/home/jicli594/work/molcrafts/molcrafts-ui` 为 source of truth：

- Page header、content section、empty/loading/error shell、layout primitive 等稳定通用模式，应先进入 `molcrafts-ui` registry，再同步到产品。
- Project、Experiment、Run、Workflow 等领域 view model、状态聚合、路由与业务 action MUST 留在 Molab。
- 不得为了减少单个 import 就把 feature-specific composite 抽成“通用组件”。
- Molab 中 vendored 的共享组件源文件 MUST 与 registry source 保持可机械校验的一致性。
- 新抽象必须至少有两个明确使用场景，或属于跨产品必须统一的 foundation；否则先保持局部实现。

## 12. Loading、Error 与 Empty State

每个 feature MUST 独立实现：

- Initial loading。
- Background refresh。
- Partial/truncated result。
- Empty result。
- Recoverable error 与 retry。
- Permission/availability state。

规则：

- Background refresh 不应清空已有数据或造成整页闪烁。
- Empty state 只有在数据成功且完整加载后才能出现。
- Error 和 empty 必须视觉、文案和行为不同。
- Onboarding empty state 必须提供下一步动作。
- Dashboard 中非关键模块失败不得使整个页面不可用。

## 13. 性能与可扩展性要求

### 13.1 必须处理的已知重复工作

1. Bootstrap 中无依赖的 slices SHOULD 并行请求。
2. Knowledge list/facets/viewer/controls MUST 共享 query cache，避免同参数重复请求。
3. Global command palette SHOULD 在首次打开或用户 intent 时加载 Knowledge。
4. Run Logs MUST 在打开 Logs 时加载；tab visibility 使用 `hasLogs` 等轻量 metadata。
5. Gantt MUST 只在 Timeline surface 可见时挂载。
6. Gantt 时间更新 SHOULD 更新必要数据，不得每个 tick dispose/recreate 整个 chart。
7. Pending approvals 的 bell、Dashboard、task inbox 与 decision bar MUST 共享 query cache；approval event stream MUST 只有一个全局 owner。
8. Feature explorer 的 query MUST 只在对应 explorer 挂载时订阅；shell 不得为了潜在页面提前订阅 Runs、Knowledge 等 feature server state。

### 13.2 Scalability 风险

以下项目需要先建立 telemetry/profile，再决定实现：

- 每 3 秒处理最多 1000 Run 并序列化完整响应。
- Asset 跨 Project fan-out/N+1。
- 大型 Project、Experiment、Run inventory 的 server pagination。
- 完整 workspace snapshot 引起的更新传播。
- 静态 plugin dependency graph。
- 大型 file tree 和 entity table 的 virtualization 阈值。

### 13.3 暂不优化

- 小型 donut/sparkline 计算。
- 简单 formatter。
- 无证据的全局 `React.memo`。
- 小列表 virtualization。
- 即将在 P0 删除的 Dashboard chart 微优化。

### 13.4 测量要求

P3 开始前 MUST 建立：

- Production bundle report。
- React Profiler 基线场景。
- Route-level request count。
- Dashboard、Runs list、Run detail 的 cold/warm load 对比。
- 100、1000 及目标上限 Run 数据规模测试。

在建立基线前，本规范不设置武断的毫秒或 bundle KB 指标。

## 14. Accessibility 与 Responsive

- 所有 icon-only navigation/action MUST 有 accessible name 和 tooltip。
- Primary navigation 必须支持 keyboard navigation 和可见 focus。
- Status 不得只依赖颜色。
- Loading、success、error 和 approval 变化 SHOULD 具有合理的 live-region 策略。
- Modal/drawer 必须正确管理 focus return。
- 动画必须尊重 `prefers-reduced-motion`。
- 窄屏下优先保留 main content；explorer 和 inspector 应变为按需 drawer，而不是压缩内容区域。

## 15. 分阶段实施计划

### P0 — Simplify

目标：先删除错误复杂度，停止继续扩展当前 Dashboard。

- 删除 Runs Overview panel manager、drag、resize 和 persisted layout。
- 删除 KPI strip、Status mix、24h Activity、Overview Gantt 和重复 feed。
- 使用 Attention + Active runs + Continue work 建立最小 Dashboard。
- 从 primary rail 移除 Activity 和 Workflows。
- 将 Copilot 从 RightPanel 移出。
- 停止从 lazy snapshot 生成权威 aggregate。
- 修复顶栏 Filter/command palette 语义。
- 消除 explorer heading、breadcrumb、page title 的重复标题。

### P1 — Information Architecture

目标：建立稳定页面职责和导航层级。

- 增加 workspace Dashboard route。
- Runs 默认进入 List，Timeline 作为按需页面。
- Workflow 迁入 Experiment。
- Assets 和 Files 进入 secondary navigation。
- Workspace explorer 重命名为 Files。
- Settings 改为 full-surface management。
- 创建动作改为 context-sensitive action。

### P2 — Component Architecture

目标：使 feature 可以独立增加和移除。

- 建立 navigation manifest/contribution。
- 拆分 LeftPanel 为 rail、explorer host 和 feature explorers。
- 拆分 RunsPage 为 route controller、list、timeline 和 dashboard feature。
- 使用统一 query layer 管理 domain server state。
- 收窄 renderer props。
- 删除未使用 Dashboard primitives、重复 EmptyState 和重复 UI source。
- Internal plugins 改为 descriptor + lazy loader。

当前 P2 落地顺序：

1. `[done]` 抽取 `molcrafts-ui` 的 `ContentSection`、`PageHeader` 与 `ExplorerShell`，并保持 registry/source 可机械比对。
2. `[done]` 以 `app/approvals` 验证 feature-owned query、command、presentation、UI、event invalidation 与 tests 的最小边界。
3. `[done]` 建立 navigation contribution descriptor，统一 route、label、placement、shell mode、path matching 与 explorer contribution，不在 manifest 中放 feature CRUD。
4. `[done]` `NavigationRail` 与 `NavigationExplorerHost` 已拆出；Projects、Runs、Agent、Knowledge、Assets、Files 及 legacy compatibility explorers 已 feature-owned。
5. `[done]` CenterPanel landing page 已迁入 lazy navigation contribution；entity inspector 共用 renderer slot resolver，Runs contextual inspector 通过 feature-owned registration 接入 shell。
6. `[done]` Renderer 使用窄化 `RendererSnapshot`/`ScopedRendererProps`；explorer 只接收声明的 command ports，Knowledge/Approvals 已迁入 scoped query cache。
7. `[done]` Internal plugins 使用轻量 descriptor 与 lazy contribution；每个 lazy surface 具有局部 loading/error/retry isolation。

### P3 — Performance

目标：处理代码已证明的重复工作，并建立测量基线。

- `[done]` 去重 Knowledge queries。
- `[done]` 并行 bootstrap slices。
- `[done]` Lazy load logs、assets、files 和重型能力。
- `[done]` 修复 Gantt 周期性重建。
- `[done]` 增加 aggregate/pagination API。
- `[done]` 建立 request、bundle 和 profiler 基线。
- `[done]` 完成 100/1000/2000 rows 测量；当前不引入 virtualization。

### P4 — Polish

目标：在语义和结构稳定后统一视觉体验。

- `[done]` 删除 card canvas/nested status cards，并清理无调用 Dashboard primitives。
- `[done]` 使用 `PageHeader`、`ContentSection` 和 workbench tokens 统一 spacing、typography 与 section hierarchy。
- `[done]` 主要 landing surface 只保留一个高强调 primary action。
- `[done]` 统一主要页面的直白 sentence-case copy。
- `[done]` 统一 empty/error/loading 的语义、wording、live status 与 retry pattern。
- `[done]` 验证 status label、focus、reduced motion 和窄屏 drawer 行为。

## 16. 受影响的主要文件与区域

| 区域 | 当前文件 | 主要修改方向 |
| --- | --- | --- |
| App shell | `apps/web/src/app/layout/AppShell.tsx` | 支持 Dashboard 与 feature-owned surfaces |
| Top context | `apps/web/src/app/layout/ContextBar.tsx` | 区分 Go to 与局部 Filter |
| Navigation | `apps/web/src/app/navigation/*`、`panels/LeftPanel.tsx` | manifest、rail renderer、explorer host 与 feature contributions |
| Feature explorers | `app/projects/ProjectsExplorer.tsx`、`app/files/FilesExplorer.tsx`、`app/assets/AssetsExplorer.tsx`、`app/agent/AgentExplorer.tsx` | feature-owned tree、actions、permissions、dialogs 与 tests |
| Center routing | `apps/web/src/app/panels/CenterPanel.tsx` | 已改为解析 lazy landing contribution 或 entity renderer slot |
| Inspector | `apps/web/src/app/panels/RightPanel.tsx`、`panels/inspectorSurface.ts` | entity inspector 使用 registry；feature contextual surface 由 owner 注册 |
| Copilot | `apps/web/src/app/components/CopilotPanel.tsx` | 移入 Agent/Attention，并明确写操作 |
| Runs | `apps/web/src/app/runs/RunsPage.tsx` | List 为默认；删除 card dashboard |
| Dashboard layout | `apps/web/src/app/runs/DashboardPanel.tsx`、`useDashboardLayout.ts` | 删除 |
| Approvals | `apps/web/src/app/approvals/*` | feature-owned query、command、SSE invalidation、review surfaces 与测试 |
| Workspace state | `apps/web/src/app/state/useWorkspaceState.ts` | Query 化、并行加载、完整性语义 |
| Entity summaries | `apps/web/src/app/renderers/entityWorkbenchData.ts` | 不从 partial snapshot 推导 total |
| Project/Experiment | `ProjectViewer.tsx`、`ExperimentViewer.tsx` | Workflow 归位、overview 降密度 |
| Run detail | `RunViewer.tsx`、`RunToolbar.tsx` | Lazy logs/assets，保持 lifecycle focus |
| Dashboard primitives | `apps/web/src/app/components/entity/Dashboard.tsx` | 删除无使用价值的通用组件词汇 |
| Knowledge | `DocTree`、`KnowledgeViewer`、`DocumentControls` | 共享 query/cache |
| Plugins | `apps/web/src/plugins/runtime.ts` | descriptor + dynamic loader |

## 17. 验收标准

### 17.1 产品与 IA

- [x] 用户进入 Molab 后，第一屏能识别 workspace 状态、待处理事项和下一步动作。
- [x] Dashboard 只包含 Attention、Active runs、Continue work 和 contextual onboarding/action。
- [x] Dashboard 不包含默认 Gantt、历史 chart、panel manager 或重复 status cards。
- [x] Workflows 不再作为 primary navigation。
- [x] Activity 不再作为缺少真实事件模型的 primary page。
- [x] Runs 默认页面是 inventory/list。
- [x] Settings、Files、Assets 不与核心 operational navigation 同权。

### 17.2 功能正交性

- [x] Workflow 只有一个主要编辑 surface，并归属于 Experiment。
- [x] Right inspector 不永久渲染 Copilot。
- [x] Run Timeline 不在 Overview 重复出现。
- [x] Global `Go to` 与 explorer `Filter` 是两个清晰控件。
- [x] 同一个 status aggregate 不在同一页面重复表达。

### 17.3 数据与架构

- [x] Project/Dashboard aggregate 来源明确且具有 completeness 语义。
- [x] Pending approvals 在 Dashboard、bell 与 Agent surfaces 之间共享 cache、mutation invalidation 和单一 event stream。
- [x] Primary、secondary 与 legacy section explorer 均通过 feature contribution 挂载，`LeftPanel` 不含领域 branching/CRUD。
- [x] Lazy load failure 不会显示为真实 empty state。
- [x] 新增 primary feature 不需要修改多个中央 switch。
- [x] Feature 能够独立挂载 route、explorer、landing 和 contextual inspector contribution。
- [x] Renderer 不再依赖完整 workspace snapshot。
- [x] Knowledge 相同 query 在一个页面生命周期内由 cache 去重。

### 17.4 性能

- [x] 独立 bootstrap requests 并行执行。
- [x] Command palette 未使用时不主动加载完整 Knowledge inventory。
- [x] Logs 在打开 Logs surface 前不下载正文。
- [x] Gantt 不在隐藏状态挂载，也不因时钟 tick 完整重建。
- [x] P3 具有可复现 request count、Profiler、bundle 对比和数据规模记录；历史 harness 缺失限制已明确记录。

### 17.5 UX 与可访问性

- [x] 每个主要页面只有一个高强调 primary action。
- [x] 主要/onboarding Empty state 提供可执行下一步或相邻 context action。
- [x] 页面标题不在 explorer、breadcrumb 和 content header 中重复三次。
- [x] 状态不只依赖颜色。
- [x] Icon-only action 具有 accessible name、tooltip 和 keyboard focus。
- [x] Explorer/inspector 在窄屏下按需显示，不压缩主要工作区。

## 18. 完成定义

本重设计只有在以下条件同时满足时才算完成：

1. 当前 Dashboard 的重复和非行动内容已经删除，而不是仅重新排列。
2. Dashboard、Runs、Experiment Workflow、Agent、Knowledge、Files 和 Settings 的职责互不重叠。
3. 数据完整性规则阻止 partial snapshot 被展示为完整事实。
4. Feature 接入不再依赖修改多个中央 closed-set 分支。
5. 已建立性能基线，优化集中在可证明的请求、渲染或规模瓶颈。
6. 视觉 polish 在新的语义和组件边界稳定后完成。

### 18.1 最终验证记录

2026-08-31 当前工作树验证：

- `apps/web` Rstest：96/96 test files、548/548 tests 通过，0 skipped、0 failed。
- TypeScript：`tsc --noEmit` 通过。
- Biome：467 files 通过，0 diagnostics。
- Production Rsbuild：通过；entry 254.2 kB raw / 65.5 kB gzip。
- Runs scale profile：100/1000/2000 rows 均完成，2000 rows p95 2.021 ms。
- `molcrafts-ui` registry：构建通过，39 items；5 个共享 source 与 Molab vendored source 零差异。
- `git diff --check`：Molab 本轮范围与 `molcrafts-ui` 均通过。
- Workspace Runs pagination 的 2 个 Python tests 在实现检查点通过；最终复跑在 test collection 前被本轮范围外的未提交 `workspace/plan.py` 与缺失 `PlanExistsError`/`PlanNotFoundError` 阻断，并非 pagination assertion failure。本轮未改写该并行中的 workspace domain 工作。
