# 启动与重编 UI

Python 安装和 UI 编译是两件事。默认的 `pip` / `uv pip` / `python -m build`
**不会**调用 npm。下面三条路径互不替代，不要合成一步。

## 日常开发（源码 checkout）

对着真实 API 做 HMR。不要重编 wheel，也不要写 `dist/`。

```bash
npm install                         # 仓库根目录，只需一次
uv pip install -e ".[dev]"          # Python 也只需一次（依赖变了才重装）

molexp serve --dev -ws ./lab --port 8000
```

打开打印出来的 **Dev UI**（默认 <http://localhost:5173>），不要打开 API
端口。`--dev` 会启动 `npm run dev:api`，把 `/api` 代理到这个进程。

`npm run dev:web` 是 MSW mock 展示页，不连接 molexp 服务。UI 端口用
`--ui-port` 覆盖，web 目录用 `MOLEXP_WEB_DIR`。

## 预览打包后的 SPA

用户从 wheel 看到的形态：单进程，运行时不需要 Node。

```bash
npm run build:web                   # 写入 src/molexp/dist/
molexp serve -ws ./lab --port 8000  # 打开 http://localhost:8000
```

可编辑安装读的就是源码树里的 `src/molexp/dist/`。跑完
`npm run build:web` 之后，**不要**再 `uv pip install`。

`dist/` 为空就是 API-only（`/api/docs`、`/api/health`）。`create_app()` 通过
`importlib.resources.files("molexp") / "dist"` 查找打包结果。

## 打 wheel

只有这条路径该带 `-C`：

```bash
uv pip install . -C build-web=true
```

这会在 setuptools 打包 `src/molexp/dist/` 之前跑 `npm run build:web`。
旧旗标 `-C build-ui=true` 会被拒绝。`src/molexp/dist/` 是 gitignored 的
（除了 `.gitkeep`）。

```
apps/web/src/  →  npm run build:web  →  src/molexp/dist/  →  setuptools  →  wheel
```

从 GitHub 安装的已发布 wheel 已经带上 UI，不需要 Node：

```bash
uv pip install git+https://github.com/MolCrafts/molexp
molexp serve -ws ./lab --port 8000
```

## 用词

| 用 | 不要用 |
|---|---|
| `npm run build:web` | `npm run build:ui` |
| `-C build-web=true` | `-C build-ui=true` |
| `molexp serve --dev` / `npm run dev:api` | 对着真实 API 跑 `npm run dev:web` |

## 相关页面

- [从 UI 开始](../getting-started/start-from-ui.md) — 终端用户的浏览器工作流
- [服务生命周期](../guide/server-lifecycle.md) — 登录、`--tunnel`、多工作区、`ServerManager`
- [`apps/web/README.md`](../../../apps/web/README.md) — 前端脚本
