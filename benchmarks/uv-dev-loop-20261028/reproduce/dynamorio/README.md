# Cargo process instruction counter

On x86-64 Linux, from the chat workspace, run the wrapper with the actual Cargo executable as its first argument. Resolve the wrapper path before changing to the uv source directory.

```sh
counter="${OHM_BENCH_WORK:-$PWD/reproduce}/dynamorio/count.py"
# In the target workspace and its configured Cargo environment:
python3 -B "$counter" -- /absolute/path/to/cargo check --offline --locked
```

The wrapper preserves stdout, stderr and the target's exit status. On success it prints one final stderr line. Parse the integer `instructions` field in the JSON after the `DynamoRIO ` prefix. `threads` maps each counted OS thread ID to its final instruction count.

## Instrumentation

The wrapper uses the official 11.3.0 x86-64 Linux release (archive SHA-256 `ae02049df5c4daeb82d4087aaa0d38bf58cdd26b38fb6042dccf27cbc32ceed9`). The built-in `drmemtrace` client increments a 64-bit TLS value once per application basic block. Zero-sized instruction and data filters retain the final cumulative count in each thread’s raw trace while omitting individual instruction fetches and memory accesses. Ordinary threads with short workloads generated 80-byte raw files here. The offline frontend execs the target in place. The wrapper selects the original PID, checks each per-thread trace header, embedded PID, final count marker and footer, and sums one count per thread. [Release](https://github.com/DynamoRIO/dynamorio/releases/tag/release_11.3.0-1), [tracer](https://github.com/DynamoRIO/dynamorio/blob/release_11.3.0-1/clients/drcachesim/tracer/tracer.cpp), [raw record format](https://github.com/DynamoRIO/dynamorio/blob/release_11.3.0-1/clients/drcachesim/common/trace_entry.h).

The underlying command is reproduced below. `scratch` must be a unique existing directory per invocation.

```sh
dr=$(dirname "$(dirname "${OHM_DRRUN:?set OHM_DRRUN to the extracted bin64/drrun}")")
scratch=$(mktemp -d)
DYNAMORIO_CONFIGDIR="$scratch" "$dr/bin64/drrun" \
  -no_follow_children -t drcachesim -offline -raw_compress none \
  -outdir "$scratch" -L0I_filter -L0I_size 0 -L0D_filter -L0D_size 0 \
  -- /absolute/path/to/cargo check --offline --locked
```

This counts user-mode Cargo and shared libraries on every Cargo thread. Forked child processes have distinct PIDs. The wrapper omits their traces, and following across exec is disabled. Kernel work, child rustc, linker and build-script work require a separate metric. A signal or fault can interrupt a counted basic block partway through. Startup and library behavior can differ across dynamic instruments. Keep both arms on one tool. The stock `inscount` sample uses a non-atomic global count and loses concurrent updates. The zero-sized online `view` run on this release discarded its final markers, so the wrapper uses offline mode. [Basic-block counting implementation](https://github.com/DynamoRIO/dynamorio/blob/release_11.3.0-1/clients/drcachesim/tracer/instru.cpp), [stock sample](https://github.com/DynamoRIO/dynamorio/blob/release_11.3.0-1/api/samples/inscount.cpp).

## Fixture calibration

```sh
counter_dir="${OHM_BENCH_WORK:-$PWD/reproduce}/dynamorio"
cc -std=c11 -O2 -Wall -Wextra -Werror -pthread "$counter_dir/fixture.c" -o "$counter_dir/fixture"
OHM_CALIBRATION_CSV="${OHM_BENCH_ROOT:?}/new-calibration.csv" python3 -B "$counter_dir/calibrate.py"
```

The fixture assigns each worker the same hand-written `decq; jnz` loop. Moving from 100,000 to 900,000 iterations gives exactly 1.6 million additional loop instructions per worker. Each of four paired replicates alternates which size is timed first. Every DynamoRIO spin sample recorded the main thread and every expected worker. Each worker's count was verified individually. The fork-and-exec case runs all loops in a child image.

| Workload | Expected delta | DynamoRIO range | Cachegrind 3.22.0 range |
| --- | ---: | ---: | ---: |
| One worker | 1,600,000 | 1,599,955–1,600,045 | 1,600,000 |
| Four workers | 6,400,000 | 6,400,000–6,400,045 | 6,399,894–6,400,042 |
| Four workers in the child only | 0 | 0 | 0 |

The `/bin/true` smoke test counted 199,536 instructions with DynamoRIO and 220,319 with Cachegrind. Median elapsed times for the four-worker 900,000-iteration fixture were 0.347 and 0.194 seconds, including launch. These timings are startup-dominated. The relative cost on Cargo needs its own measurement. The 50 fixture and smoke samples are recorded in `calibration.csv`.
