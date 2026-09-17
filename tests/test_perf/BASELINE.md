# Perf baseline — small scale (5 projects × 4 experiments × 10 runs = 200 runs)

Captured 2026-09-16 with `scratchpad/capture_baseline.py` (one cold `Workspace` per route; *warm* = the same client's second request).

Columns: `fs *` = calls through the `FileSystem` seam (`CountingFileSystem`); `os open *` = every read-only file open in the process (`sys.addaudithook`, sees raw `pathlib`/sqlite too); `os listings` = `os.listdir`/`os.scandir` events.

## BEFORE — pristine `HEAD` (e0ebdec7) checked out in a scratch worktree, fixture build 4.1 s

| route | phase | s | fs open | fs exists | fs is_dir | fs stat | fs listdir | os open assets.json | os open run.json | os open meta.yaml | os open total | os listings | listings under executions/ | event rows materialized |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `workspace_runs` | cold | 0.606 | 631 | 606 | 251 | 0 | 20 | 0 | 600 | 0 | 634 | 21 | 0 | 0 |
| `workspace_runs` | warm | 0.424 | 606 | 606 | 226 | 0 | 20 | 0 | 600 | 0 | 606 | 20 | 0 | 0 |
| `run_detail` | cold | 0.027 | 7 | 4 | 3 | 0 | 0 | 0 | 6 | 0 | 9 | 0 | 0 | 0 |
| `run_detail` | warm | 0.008 | 4 | 4 | 0 | 0 | 0 | 0 | 5 | 0 | 5 | 0 | 0 | 0 |
| `experiment_runs` | cold | 0.024 | 49 | 47 | 13 | 0 | 1 | 0 | 57 | 0 | 59 | 1 | 0 | 0 |
| `experiment_runs` | warm | 0.025 | 47 | 47 | 11 | 0 | 1 | 0 | 57 | 0 | 57 | 1 | 0 | 0 |
| `run_files` | cold | 0.121 | 3 | 0 | 3 | 0 | 0 | 226 | 1 | 0 | 229 | 34 | 3 | 0 |
| `run_files` | warm | 0.136 | 0 | 0 | 0 | 0 | 0 | 226 | 0 | 0 | 226 | 34 | 3 | 0 |
| `asset_lineage` | cold | 34.180 | 90626 | 90626 | 191277 | 0 | 10426 | 181026 | 0 | 0 | 181027 | 20826 | 0 | 0 |
| `asset_lineage` | warm | 31.481 | 90626 | 90626 | 191277 | 0 | 10426 | 181026 | 0 | 0 | 181026 | 20826 | 0 | 0 |
| `workspace_info` | cold | 0.093 | 6 | 1 | 6 | 0 | 0 | 226 | 0 | 0 | 232 | 26 | 0 | 0 |
| `workspace_info` | warm | 0.026 | 1 | 1 | 1 | 0 | 0 | 226 | 0 | 0 | 227 | 26 | 0 | 0 |
| `knowledge_list` | cold | 3.304 | 0 | 0 | 0 | 0 | 0 | 0 | 440 | 2096 | 4091 | 2565 | 1200 | 0 |
| `knowledge_list` | warm | 1.654 | 0 | 0 | 0 | 0 | 0 | 0 | 440 | 2096 | 4057 | 2558 | 1200 | 0 |
| `knowledge_search` | cold | 0.705 | 0 | 0 | 0 | 0 | 0 | 0 | 220 | 1273 | 2321 | 1279 | 600 | 0 |
| `knowledge_search` | warm | 0.900 | 0 | 0 | 0 | 0 | 0 | 0 | 220 | 1273 | 2321 | 1279 | 600 | 0 |
| `events` | cold | 0.045 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 468 |
| `events` | warm | 0.024 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 468 |
| `workspace_context` | cold | 0.761 | 631 | 606 | 251 | 0 | 20 | 226 | 820 | 1048 | 2899 | 1325 | 600 | 0 |
| `workspace_context` | warm | 0.693 | 606 | 606 | 226 | 0 | 20 | 226 | 820 | 1048 | 2874 | 1325 | 600 | 0 |

## AFTER — live tree while P1 was landing (memo, try-read, scoped scan, events LIMIT, knowledge single walk), fixture build 2.17 s

| route | phase | s | fs open | fs exists | fs is_dir | fs stat | fs listdir | os open assets.json | os open run.json | os open meta.yaml | os open total | os listings | listings under executions/ | event rows materialized |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `workspace_runs` | cold | 0.107 | 431 | 0 | 0 | 406 | 20 | 0 | 400 | 0 | 434 | 21 | 0 | 0 |
| `workspace_runs` | warm | 0.108 | 0 | 0 | 0 | 406 | 20 | 0 | 0 | 0 | 0 | 20 | 0 | 0 |
| `run_detail` | cold | 0.035 | 4 | 0 | 3 | 3 | 0 | 0 | 2 | 0 | 5 | 0 | 0 | 0 |
| `run_detail` | warm | 0.024 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `experiment_runs` | cold | 0.004 | 22 | 0 | 2 | 30 | 1 | 0 | 20 | 0 | 22 | 1 | 0 | 0 |
| `experiment_runs` | warm | 0.050 | 0 | 0 | 0 | 30 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| `run_files` | cold | 0.044 | 3 | 0 | 3 | 1 | 0 | 1 | 1 | 0 | 4 | 9 | 3 | 0 |
| `run_files` | warm | 0.023 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 9 | 3 | 0 |
| `asset_lineage` | cold | 0.065 | 0 | 0 | 0 | 0 | 0 | 226 | 0 | 0 | 227 | 252 | 0 | 0 |
| `asset_lineage` | warm | 0.062 | 0 | 0 | 0 | 0 | 0 | 226 | 0 | 0 | 226 | 252 | 0 | 0 |
| `workspace_info` | cold | 0.063 | 7 | 0 | 0 | 1 | 1 | 1 | 0 | 0 | 7 | 1 | 0 | 0 |
| `workspace_info` | warm | 0.010 | 1 | 0 | 0 | 1 | 1 | 1 | 0 | 0 | 1 | 1 | 0 | 0 |
| `knowledge_list` | cold | 0.183 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 278 | 338 | 286 | 0 | 0 |
| `knowledge_list` | warm | 0.129 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 278 | 305 | 279 | 0 | 0 |
| `knowledge_search` | cold | 0.125 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 278 | 530 | 279 | 0 | 0 |
| `knowledge_search` | warm | 0.236 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 278 | 530 | 279 | 0 | 0 |
| `events` | cold | 0.019 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 50 |
| `events` | warm | 0.027 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 50 |
| `workspace_context` | cold | 0.149 | 431 | 0 | 0 | 406 | 20 | 226 | 400 | 278 | 962 | 551 | 0 | 0 |
| `workspace_context` | warm | 0.152 | 0 | 0 | 0 | 406 | 20 | 226 | 0 | 278 | 531 | 551 | 0 | 0 |

## Notes

- `asset_lineage` BEFORE: 34 s and 181 026 `assets.json` opens for one request at 200 runs — one full manifest scan per lineage node (`lineage.py` + `routes/asset.py:_node`). AFTER: one scan (226 = 1+P+E+N manifests).
- `workspace_runs` BEFORE: 3 opens/run + `exists`/`is_dir` probes per run on every request. AFTER: 2 opens/run cold, 0 opens warm (2 stats/run — memo validation of `run.json` + `_ops/run.json`).
- `knowledge_list` / `workspace_context` still list every `executions/` dir (`listings under executions/` = 1200 / 600) until the `Bundle` prune lands; `test_list_never_enters_run_internals` locks the target.
- `events` BEFORE materialized all 468 rows for `limit=50`; AFTER exactly 50 because `list_rows` applies `LIMIT` in SQL — the budget test asserts `0 < rows ≤ limit`.
- Full scale (`MOLAB_PERF_SCALE=full`, 10 000 runs): fixture build + parse-back 134 s on this NFS mount (I/O bound, ~35 % CPU; the 25 k single-row sqlite event appends are the dominant share).
