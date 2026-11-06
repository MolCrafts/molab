# Tracking a Computation

A computation leaves more behind than its return value. What it prints and what it measures are part of the record, and molab keeps both with the attempt that produced them. Each execution manages its own stdio: while an attempt runs, it is the *current execution* of the code inside it, and what that code prints through `molab.print` is appended to the attempt's `stdout.log` and `stderr.log`.

## The current execution

An attempt becomes current when its context is entered and stops being current when it exits. That holds for every way an attempt runs:

- `with run.start() as ctx:` in a driver script;
- `run.execute(workflow)` and `molab run`, where every task body runs inside the attempt's context;
- a sweep (`RunSet.execute`), where each run's attempt is current only for its own tasks.

`molab.current()` returns the current execution, or `None` outside one. A context entered inside another is current until it exits, and then the outer one is current again.

The current execution is held in a [context variable](https://docs.python.org/3/library/contextvars.html). A workflow task body, sync or async, inherits it: the engine runs each body as its own asyncio task, and a sync body runs through `asyncio.to_thread`, which copies the context. Two executions in one process never see each other. A thread you start yourself starts with an empty context, so hand it the current one when you want its prints recorded:

```python
import contextvars
import threading

context = contextvars.copy_context()
threading.Thread(target=context.run, args=(worker,)).start()
```

## `molab.print`

```python
from molab import print

with run.start() as ctx:
    print("step 1 converged")  # terminal + executions/eNN/stdout.log
    print("energy drifted", file=sys.stderr)  # terminal + executions/eNN/stderr.log
```

`molab.print` has the builtin's signature, `print(*values, sep=" ", end="\n", file=None, flush=False)`, and its behaviour. It always writes to the original target first, so what you see in the terminal (or in the scheduler's output file) is unchanged. Then, inside an execution, it appends the same text to the attempt's files:

| `file=` | copied to |
|---|---|
| `None` or `sys.stdout` | `executions/eNN/stdout.log` |
| `sys.stderr` | `executions/eNN/stderr.log` |
| anything else | not copied |

Outside an execution it is the builtin, so the same module runs unchanged without molab. Text is written as given, with no timestamp prefix. One call is one locked write, so lines printed from parallel tasks never break apart. Writes are buffered; `flush=True` also flushes the log file, and the attempt closes both files when it exits, before the seal hashes them into `Execution.evidence`. If the copy fails (a full disk, say), the original output still appears, the failure is logged once, and your code carries on.

The import shadows the builtin in that module on purpose. Nothing is captured at the file-descriptor level and `sys.stdout` is never replaced, so a plain `print` (or a C extension writing to fd 1) is not recorded. `from molab import *` also imports `print`, which has the same effect.

## `ctx.log`

`ctx.log("stdout")` and `ctx.log("stderr")` append whole lines to the same two files, through the same handles and locks, so a line appended there never splits a printed one. `ctx.log("run")` is the attempt's own log, `run.log`, where molab records the start, the finish, and a failure's traceback.

```python
with run.start() as ctx:
    ctx.log("run").append("loaded 3 structures")
    ctx.log("stdout").append("epoch 1")
    ctx.log("stdout").tail(20)  # the last 20 lines
```

**Where it shows up.** A run's **Logs** tab shows one attempt's logs, one stream at a time: `stdout`, `stderr` (in red) or `run`. It reads each stream incrementally through `…/logs/{stream}?offset=`, polls only while the attempt is active, and follows the bottom unless you have scrolled up. A stream with nothing in it says so ("No stderr captured."). The browser keeps the last 2 MB of a stream; past that, the head is dropped and a link opens the whole `stdout.log`, `stderr.log` or `run.log`.

## Metrics

`ctx.metrics` writes measurements as the computation runs, the way TensorBoard does. Each call appends one record to the attempt's `executions/eNN/metrics.mlp.jsonl` at once, beside `run.log`, so a chart of a running attempt is current. There is one writer per attempt, and a driver script and a workflow task reach the same one. The file is evidence. It is not an asset.

```python
with run.start() as ctx:
    for step in range(100):
        loss = train_one_step()
        ctx.metrics.scalar("loss", loss, step)
    ctx.metrics.histogram("forces", bins=[0.0, 0.5, 1.0], counts=[12, 3], step=99)
    ctx.metrics.text("note", "lr halved at step 50", step=50)
    ctx.metrics.json("config", {"lr": 1e-3, "batch": 32})
    ctx.metrics.image("rdf", Path("rdf.png"), step=99, caption="g(r)")
```

| method | record `t` | value `v` |
|---|---|---|
| `scalar(key, value, step=None)` | `scalar` | a finite number |
| `histogram(key, bins, counts, step=None)` | `histogram` | `{"bins": [...], "counts": [...]}` |
| `text(key, text, step=None)` | `text` | a string |
| `json(key, value, step=None)` | `json` | any JSON value |
| `image_ref(key, path, step=None, caption=None)` | `image_ref` | `{"path": ..., "caption": ...}` |
| `image(key, data, step=None, caption=None, name=None)` | `image_ref` | as above, for an archived copy |

Every method also takes `wall_time=` and `tags=`, and returns the record it wrote. `wall_time` defaults to now, in UTC. `image` registers the image as an asset first: `data` is a path to an existing file, or the image's bytes together with `name=`. The `image_ref` record's path is `molab:asset/<id>` when the owner registered it. Each image is its own asset, so give each one its own title. `image_ref` alone records a path and registers nothing. `ctx.register_metric(key, value, step=None)` appends a scalar. The WAL itself stays at the attempt root and is not registered.

**Where it shows up.** The run's **MolPlot** tab gives each key its own card, by record type. A scalar is a series tile with its chart. A histogram is a bar chart of the latest step, with a slider over the steps it was written at. A text key lists its entries newest first, each one folding. A JSON key shows its latest value as a folding tree, with a step picker. An image key is a gallery in step order, with the step and caption under each thumbnail; clicking one opens it in the image viewer. The thumbnails are read through the attempt's file route, so only an attempt-relative path (what `image` records) can be shown. The tab's badge counts keys of every type. Charts thin scalars and histograms to one point every 10 000 steps per key; text, JSON and image records are never thinned.

### From a workflow task

A task body reaches the same writer as `ctx.metrics`:

```python
@wf.task
def train(ctx, epochs: int = 10):
    for epoch in range(epochs):
        ctx.metrics.scalar("loss", fit_one_epoch(), epoch)
    return {"epochs": epochs}
```

Each record written inside a task carries `tags.task`, the task's name, so same-level tasks running in parallel each label their own records. A `task` key you pass in `tags` wins. `ctx.register_metric` keeps its deferred semantics in a task: the scalar is appended when the body returns, and it carries `tags.task` too.

**Where it shows up.** When records carry `tags.task`, the MolPlot tab shows a row of task chips (`all` and one per task). Picking a task narrows every card, of every type, to the records that task wrote.

Without molab (no execution is current), `ctx.metrics` keeps the records in memory instead, as `ctx.metrics.records`, and `image` records only the reference. The same body runs either way.

### Node-cache replay

When an attempt runs a task, the node cache stores the metric records the task wrote alongside its result. When a later attempt hits that entry, the task does not run again, but its records are appended to the new attempt's WAL as they were (same `s` and `w`), each with `tags.replayed_from` naming the attempt that produced them. Curves of a cached attempt are therefore complete, and a chart can still tell which points were measured in this attempt. A task that writes more than 50 000 records is not replayed, and neither is an entry written before this was added.

**Where it shows up.** A series or card that holds replayed records carries a small "replayed from e01" marker, naming the attempt that measured them.

## Commands

`CommandTask` captures its child's stdout and stderr. Inside an execution it also appends them to `stdout.log` / `stderr.log` when the command returns, whether it succeeded or failed. The task's return value is unchanged.

The child also gets the attach variables described below (`MOLAB_EXECUTION_DIR`, `MOLAB_TASK`), so a Python child that calls `molab.track()` writes metrics and artifacts into the same attempt. A key in the task's `env=` wins over them. Because `CommandTask` already archives the child's streams, the child is told so (`MOLAB_STDIO_CAPTURED=1`) and its `molab.print` lines are recorded once, through the capture.

## Plain scripts and child processes

Code that is not a molab task gets the same surface through `molab.track()`. It returns a tracker with `print` routing, `.metrics` (the same methods as `ctx.metrics`), `emit_artifact(data, *, name=None, media_type=None, semantic_type=None, tags=None)` and `child_env()`, and it works as a context manager in every case. It decides in this order.

1. **An execution is current** (inside `run.start()`, a workflow task, or after an earlier `track()`): it returns that one, unchanged, and `with` around it does nothing.

    ```python
    with run.start() as ctx:
        assert molab.track() is ctx
    ```

2. **The process is a child of a molab execution** (`MOLAB_EXECUTION_DIR` is set): it returns an attached tracker, current for the whole process, and `with` does nothing. Prints go to the parent attempt's `stdout.log` / `stderr.log` and metrics to its `artifacts/metrics.mlp.jsonl`, each appended with `O_APPEND`, and every record carries `tags.task` from `MOLAB_TASK`. An artifact is only *staged*: copied into `work/_molab/staged/<n>-<basename>` with one line in `work/_molab/artifacts.jsonl`. The parent records the staged artifacts at `artifacts/<name>` when it seals, with `metadata.staged_by="child"` and `metadata.task`; the child never writes `execution.json`. Attaching to a sealed attempt raises. The child re-reads the seal at most every 5 seconds before a write, and after it a print or a metric is dropped with one warning (never an exception), while `emit_artifact` raises. Launch a child from your own code by merging `child_env()` into its environment:

    ```python
    import os
    import subprocess

    import molab

    with run.start() as ctx:
        subprocess.run(
            ["python", "train.py"],
            env={**os.environ, **molab.current().child_env()},
            check=True,
        )
    ```

    and in `train.py`:

    ```python
    import molab
    from molab import print

    t = molab.track()
    print("epoch 1")
    t.metrics.scalar("loss", 0.31, step=1)
    t.emit_artifact("model.pt", semantic_type="model")
    ```

3. **`project` and `experiment` are given and the working directory is inside a workspace**: it opens the experiment (by name, creating it the first time), adds a run with `params`, and enters `run.start()`. This is a live attempt in this process, and the first `with` around it seals it on exit. Without a `with` it is sealed at interpreter exit, as failed when an uncaught exception ended the script.

    ```python
    import molab
    from molab import print

    with molab.track(project="tg", experiment="cooling", params={"rate": 10}) as t:
        print("quenching")
        t.metrics.scalar("density", 1.02, step=0)
    ```

4. **Otherwise**: it writes the same layout into a plain directory, `./molab-track` unless you pass one, and is current for the whole process. Use this for a scratch script or an `sbatch` job you submitted by hand.

    ```python
    import molab
    from molab import print

    t = molab.track("runs/rate-10")
    print("quenching")
    t.metrics.scalar("density", 1.02, step=0)
    t.emit_artifact("final.data", semantic_type="structure")
    ```

    The directory holds `stdout.log`, `stderr.log`, `artifacts/metrics.mlp.jsonl`, the staged files and their manifest under `work/_molab/`, and `work/_molab/track.json` (start time, host, pid, argv, Python, working directory). Its `finished_at` is written at interpreter exit, by `t.close()`, or when a `with` around the tracker exits. Fold it into a run afterwards:

    ```bash
    molab runs adopt tg cooling rate=10 --from runs/rate-10 --params '{"rate": 10}'
    ```

    The adopted attempt is sealed with `stdout.log` / `stderr.log` at its root, the WAL registered as the `molplot.metrics` Artifact, and each staged file at `artifacts/<name>` as an Artifact (`metadata.staged_by="offline"`). The start and finish come from `track.json` unless you pass `--started` / `--finished`. Everything else in the directory (`work/`) stays where it is. A refused adoption, for example two files landing on the same name, moves everything back. In Python the same thing is `run.adopt_execution(started_at=…, finished_at=…, tracked="runs/rate-10")`.

## Reading the logs

The server reads the files that exist. `GET …/runs/{run_id}/executions/{execution_id}/logs` returns the whole `stdout` and `stderr`. Older attempts that have no `stdout.log` fall back to the scheduler files under `jobs/`. To follow one log incrementally, call `GET …/executions/{execution_id}/logs/{stream}?offset=N` with `stream` one of `stdout`, `stderr` or `run`: each call returns at most 256 KiB from `offset`, plus `nextOffset`, `size` and `eof`, and a poller passes `nextOffset` back as the next `offset`.
