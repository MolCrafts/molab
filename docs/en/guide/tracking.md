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

## Metrics

`ctx.metrics` writes measurements as the computation runs, the way TensorBoard does. Each call appends one record to the attempt's `executions/eNN/artifacts/metrics.mlp.jsonl` at once, so a chart of a running attempt is current. There is one writer per attempt, and a driver script and a workflow task reach the same one.

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

Every method also takes `wall_time=` and `tags=`, and returns the record it wrote. `wall_time` defaults to now, in UTC. `image` archives the image first: `data` is a path to an existing file, or the image's bytes together with `name=`. It becomes an Artifact of the attempt with `semantic_type="molplot.image"`, and the `image_ref` record points at that Artifact's path (`artifacts/<name>`), so the image is kept with the attempt rather than referenced where it happened to be. Each image is its own Artifact, so give each one its own name. `image_ref` alone records a path and archives nothing. When the attempt exits, the WAL itself is registered as an Artifact (`semantic_type="molplot.metrics"`) if anything was written to it. `ctx.register_metric(key, value, step=None)` is still there and appends a scalar.

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

Without molab (no execution is current), `ctx.metrics` keeps the records in memory instead, as `ctx.metrics.records`, and `image` records only the reference. The same body runs either way.

### Node-cache replay

When an attempt runs a task, the node cache stores the metric records the task wrote alongside its result. When a later attempt hits that entry, the task does not run again, but its records are appended to the new attempt's WAL as they were (same `s` and `w`), each with `tags.replayed_from` naming the attempt that produced them. Curves of a cached attempt are therefore complete, and a chart can still tell which points were measured in this attempt. A task that writes more than 50 000 records is not replayed, and neither is an entry written before this was added.

## Commands

`CommandTask` captures its child's stdout and stderr. Inside an execution it also appends them to `stdout.log` / `stderr.log` when the command returns, whether it succeeded or failed. The task's return value is unchanged.

## Reading the logs

The server reads the files that exist. `GET …/runs/{run_id}/executions/{execution_id}/logs` returns the whole `stdout` and `stderr`. Older attempts that have no `stdout.log` fall back to the scheduler files under `jobs/`. To follow one log incrementally, call `GET …/executions/{execution_id}/logs/{stream}?offset=N` with `stream` one of `stdout`, `stderr` or `run`: each call returns at most 256 KiB from `offset`, plus `nextOffset`, `size` and `eof`, and a poller passes `nextOffset` back as the next `offset`.
