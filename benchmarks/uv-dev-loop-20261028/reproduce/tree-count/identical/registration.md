# Prospective same-input, same-state edited uv cohort

The first admission trial is separately preserved in `../summary.md`. It compared a structural edit against the next literal edit and rejected the check workload. This new registration separates those transitions. It uses the same calibrated Cargo, rustc and Wild counters and their documented exclusions.

For each endpoint, start with the unmodified retired private fixture. Warm baseline Cargo with the fixed wrappers and `-j8`. Apply the direct new expression `uv-preview-D00`, build it natively, then require a second invocation to be fresh. Park that target as the common D00 predecessor. Make four `cp -a --reflink=auto` copies from it. Write the new literal `uv-preview-D01` exactly once at the same source path. The four cells run the same source bytes and timestamp at the same visible target path in this order: native baseline, counted candidate, native candidate, counted baseline.

Each native cell has an independent successful-exec census. Require exact rustc argv multisets, Wild link-output multisets, one Cargo executable, the same package work and identical test executable rosters in all four cells. Require real uv compilation, a successful command, no network activity and no test execution. A same-state mismatch stops that endpoint. Record exclusions without drawing an effect estimate from rejected observations. Continue the other endpoints independently.

For admitted endpoints only, keep the separate counted baseline/candidate targets. Give both arms the same eight new same-length literals, `D10` through `D17`, in order. Recheck the frozen D01 workload on every observation. Within each pair, four orders are baseline-first and four are candidate-first. `random.Random(seed).shuffle` permutes them, using 38181311 (check), 38181317 (build) and 38181341 (test). The point estimate is the median paired proportional reduction in the sum of the three role instruction counts. A two-sided exact sign p < .05/3 and a positive point estimate are required for a directional result. This optional cohort has no independent repeat. Pair timing is not a performance metric. CPU affinity is 16–23 throughout, with the host's concurrent background compilation permitted.

```sh
taskset -c 16-23 /usr/bin/python3 -B work/tree-count/identical.py pilot check
taskset -c 16-23 /usr/bin/python3 -B work/tree-count/identical.py samples check
# Repeat with build and test. Only run samples for an endpoint whose pilot passed.
```
