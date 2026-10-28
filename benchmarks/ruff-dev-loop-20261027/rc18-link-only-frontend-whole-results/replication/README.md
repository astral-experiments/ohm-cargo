# Independent Ruff whole-command timing on Linux x86_64

Two separately trained batches compared adjacent ordinary runs of `cargo +ohm test --workspace --no-run --locked --offline -j8 --message-format=json`. Each batch started with empty target and Cargo build directories for both arms. Both arms used the same effective source, tool and output paths. The source, two Cargo images, released Ohm -18 compiler and stock Wild matched the first machine. The scores below come exclusively from this host.

| Batch | Pairs | Control median | Candidate median | Paired reduction | Candidate faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 24 | 9.404 s | 9.097 s | 0.97% | 14/24 |
| 2 | 24 | 9.778 s | 9.402 s | 3.29% | 14/24 |
| Both | 48 | 9.565 s | 9.280 s | 2.14% | 28/48 |

The 95% batch-stratified bootstrap interval for the geometric paired reduction was -7.06% to 10.38%. The two-sided paired sign test gave p = 0.312326807. The independent machine did not pass its registered timing criteria.

All 96 measured commands exited successfully with 619 units and 563 fresh. Eight unscored process traces bracketed the two batches. In each trace the complete `ron` compile used eight frontend threads, all 50 cached Rust invocations ran, and GCC, collect2 and stock Wild each produced the same 50 named output files. The last automatic frontend flag on each cached invocation changed from `-Zthreads=8` to `-Zthreads=1`. Every other compiler argument matched across arms within the batch.

Each arm listed the same 200 e2e tests and passed both original notebook tests before and after its timed batch. The historical edited-source and clean/restore controls are in the independently sealed first-machine functional packet. On this host all four cold seeds used the original Ruff source.

Only the ordinary Cargo process was timed. Setup, hashing, tracing, program execution, host checks and JSON parsing occurred outside its timer. All 48 pairs, their command-output and process receipts, the prespecified schedule, and the original analysis are included. The complete ELF hashes are retained separately for each native qualification.

Run `python3 -IB verify.py` to authenticate the files, validate each raw pair and all eight native captures, and recompute the statistics.
