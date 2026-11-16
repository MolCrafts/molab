---
title: Molab 前端性能基线
description: Dashboard 重设计 P3 的请求、React 渲染、bundle 与 Runs 数据规模基线。
---

# Molab 前端性能基线

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-08-31 |
| 范围 | `apps/web` Dashboard、Runs list、Run detail |
| 环境 | Rsbuild dev mock、headless Firefox、Linux |
| 目的 | 记录可复现基线，区分实际问题、scalability 风险和不值得优化的工作 |

## 1. 结论

本轮性能工作的主要收益来自删除无效工作，而不是给现有组件普遍增加 memo：

- Internal plugin 从静态重型依赖图改成 descriptor + dynamic import，entry chunk raw/gzip 均下降约 60%。
- 无依赖 bootstrap slices 已并行；Project 列表只等待 Workspace，Assets 只在 Assets surface 按需加载。
- Knowledge list 使用共享 TanStack Query cache，command palette 未打开时不再请求完整 inventory。
- Logs、Timeline/Gantt、metrics、preview 和重型 plugin surface 只在用户打开对应 surface 时加载。
- Workspace Runs API 支持 `offset`/`limit`，并在分页前计算真实 `total` 与 aggregate。
- 100–2000 rows 的前端 filter + facets + sort + first-page pipeline p95 约 0.6–2.0 ms；当前没有证据支持引入 virtualization。
- Profiler 发现并修复了 canonical Run deep link 只显示空壳、未 hydrate Project → Experiment → Run 的功能缺陷。

当前应继续观察的真实 scalability 风险是：后端 `/api/workspace/runs` 仍会在每次轮询时扫描所有 Run 以计算 aggregate。分页已减少响应 payload，但尚未减少服务端扫描成本。

## 2. 测量方法

### 2.1 React 与请求

`RouteProfiler` 只在 URL 包含 `?profile=1` 时挂载，普通用户路径没有 Profiler subtree。采样器记录：

- 最近 200 个 React commit 的 `actualDuration`、`baseDuration` 和 `commitTime`。
- Resource Timing 中每条 `/api/` 路径的唯一集合和实际出现次数。
- 数据同时写入 `window.__MOLAB_REACT_PROFILE__`、`window.__MOLAB_ROUTE_REQUESTS__` 和 localStorage，便于无头浏览器读取。

本报告把 `commitTime < 6000 ms` 记为 cold window，把其余 commit 记为 steady window。这里的 cold/warm 是应用路由生命周期划分，不等同于生产网络、浏览器 HTTP cache 或真实用户 paint 指标。

### 2.2 Runs 数据规模

运行：

```bash
cd apps/web
../../node_modules/.bin/tsx scripts/profile-runs-data.ts
```

脚本对 100、1000、2000 rows 执行与 Runs list 相同类别的 filter、facet、sort 和 first-page pipeline，并报告 median/p95。

### 2.3 JS bundle 体积

使用 production Rsbuild 输出的 raw/gzip 资产统计。对比点是本轮 internal plugin lazy split 前后的同一工作树检查点；总 bundle 包含异步 WASM/visualization 资产，不能当作首屏下载量。

## 3. React Profiler 基线

单位为 ms；duration 取 React `actualDuration`。

| Route | Window | Commits | Median | P95 | Max |
| --- | --- | ---: | ---: | ---: | ---: |
| Dashboard `/` | all | 35 | 1 | 10 | 25 |
| Dashboard `/` | cold | 27 | 1 | 10 | 25 |
| Dashboard `/` | steady | 8 | 1 | 3 | 3 |
| Runs `/runs` | all | 44 | 1 | 10 | 31 |
| Runs `/runs` | cold | 36 | 1 | 11 | 31 |
| Runs `/runs` | steady | 8 | 1 | 4 | 4 |
| Run detail | all | 29 | 1 | 14 | 24 |
| Run detail | cold | 26 | 1 | 14 | 24 |
| Run detail | steady | 3 | 1 | 1 | 2 |

Run detail 使用：

```text
/projects/protein-folding/experiments/exp-001/runs/n=8
```

结论：当前 mock 数据下没有持续的大型 React commit。Dashboard/Runs 的 steady commit 来自轮询数据；Run detail hydrate 后基本静止。这里没有包含浏览器 layout/paint、网络 RTT、Python 后端 I/O 或 WASM 内部执行时间，因此不能用这些数值声称真实生产 TTI。

## 4. Route request 基线

采样窗口内结果：

| Route | API requests | Unique paths | 主要周期请求 |
| --- | ---: | ---: | --- |
| Dashboard | 21 | 13 | cache status 6；workspace runs 4 |
| Runs list | 21 | 13 | cache status 6；workspace runs 4 |
| Run detail | 18 | 14 | cache status 5；其余均 1 |

Dashboard 与 Runs 的一次性路径为：auth status、agent tasks、approvals、workspaces、workspace info、workspace files、projects、plugin catalog，以及 example plugin manifest/bundle。`/api/approvals/events` 只有一个全局 owner。

Run detail 在公共 bootstrap 之外只增加两条层级 hydration 请求，且各出现一次：

```text
/api/projects/protein-folding/experiments
/api/projects/protein-folding/experiments/exp-001/runs
```

请求变化的可检查证据：

- 旧 bootstrap 对 slices 使用顺序 `for`；当前把 workspaces、workspace tree、agent sessions 放入同一 `Promise.all` level，再加载依赖 workspaces 的 projects。
- 旧 command palette 挂载即调用 Knowledge list；当前只有 `open && mode === "goto"` 时启用 query，默认路由减少 1 个 eager Knowledge request。
- Assets 的 workspace/project fan-out 已从 bootstrap 移到 Assets view，其他路由为 0。
- Logs query 以 Logs surface 的 `enabled` 状态为门；默认 Run Overview 为 0。
- 本轮新增的 deep-link hydration 把 Run detail 从“12 条唯一路径但没有实体数据的空壳”修正为“14 条唯一路径且父链完整”。这 2 次请求是必要数据，不属于性能回退。

限制：P3 实施前没有 request-count/Profiler harness，且当前工作树包含其他未提交工作，不能安全回退后生成完全同条件的历史数字。因此 bundle 有直接 before/after 数值；request 与 React 表以当前可复现基线为准，请求优化以代码路径和当前计数记录。后续变更必须用同一 harness 做数值对比。

## 5. bundle 对比

| Metric | Lazy split 前 | Lazy split 后 | 变化 |
| --- | ---: | ---: | ---: |
| Entry `index` raw | 638.6 kB | 254.2 kB | -60.2% |
| Entry `index` gzip | 163.4 kB | 65.5 kB | -59.9% |
| Shared chunk raw | 1372.2 kB | 708.4 kB | -48.4% |
| Shared chunk gzip | 407.2 kB | 211.1 kB | -48.2% |
| Entry + shared raw | 2010.8 kB | 962.6 kB | -52.1% |
| Entry + shared gzip | 570.6 kB | 276.6 kB | -51.5% |
| 所有同步/异步资产 raw | 34,143.4 kB | 34,270.0 kB | +0.4% |
| 所有同步/异步资产 gzip | 10,202.0 kB | 10,268.7 kB | +0.7% |

总资产略增是 chunk boundary、lazy wrapper 和 descriptor runtime 的成本，不代表 cold-load 回退。首屏不再执行 editor、workflow、knowledge、molplot、molq、molvis、tensorboard、deltaf 的重型实现。两个约 5.85/6.69 MB WASM 和约 6.87/8.22 MB visualization chunks 仍然很大，但保持异步；只有实际打开相关 surface 才应继续优化它们。

## 6. Runs 数据规模

| Rows | Median | P95 |
| ---: | ---: | ---: |
| 100 | 0.077 ms | 0.558 ms |
| 1000 | 0.636 ms | 1.699 ms |
| 2000 | 1.300 ms | 2.021 ms |

决定：当前不引入 virtualization。虚拟化会增加 keyboard、selection、sticky header、动态高度与测试复杂度，而 2000 rows 的纯数据 pipeline 尚未构成瓶颈。以下任一条件出现后重新评估：

- 目标上限超过 2000 可见 rows。
- 浏览器 Profiler 显示 table commit/paint 成为主要耗时。
- 真实设备滚动丢帧或内存占用可重复超标。

## 7. 问题分级

### 7.1 已处理的实际问题

- Internal plugin 静态进入启动依赖图。
- Knowledge inventory eager request 与跨组件重复 query。
- Bootstrap 独立 slices waterfall。
- Logs、Gantt、metrics 和 preview 在非活动 surface 做工作。
- Run deep link 未 hydrate lazy hierarchy。
- Workspace Runs response 缺少 offset 和真实分页 aggregate。

### 7.2 仍需 telemetry 的 scalability 问题

- `/api/workspace/runs` 每次 aggregate 仍扫描完整 workspace inventory。
- Assets 页面按 Project fan-out；当前只在 contextual Assets surface 发生。
- 超大型 file tree、entity inventory 的 DOM/内存压力。
- 异步 Molvis/Molplot/WASM 在首次实际使用时的下载和初始化成本。

### 7.3 当前不值得优化

- 小型 formatter、facet map 和简单 status projection。
- 无证据的全局 `React.memo`。
- 2000 rows 以下的 list virtualization。
- 已从 Dashboard 删除的 chart、KPI 和 layout-manager 微优化。

## 8. 后续性能门槛

新 feature 合入前至少回答：

1. 是否增加默认 route 的 API request 或 polling owner？
2. 是否把重型依赖带回 entry/shared chunk？
3. 非活动 surface 是否仍会订阅 server state、timer 或 event stream？
4. 大数据路径是否有 server pagination/completeness 语义？
5. 是否能通过 `?profile=1` 和本脚本复现优化依据？

没有测量证据时，不新增 virtualization、全局 memo、复杂 cache 或新的 Dashboard analytics。
