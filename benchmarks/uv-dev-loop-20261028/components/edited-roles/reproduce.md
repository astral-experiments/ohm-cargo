# Reproduce the same-state edited instruction cohorts

Follow the combined archive's `reproduce/first-five.md` on x86-64 Linux. It stages pinned uv `c22e6b71933443e9cd299d4b6ac8de035ed4825b`, Ohm 1.99.0-17, DynamoRIO 11.3.0-1 and a private offline registry. Also install `strace`, GNU coreutils and a C compiler. The work and benchmark roots must share a filesystem for hard links. Each endpoint needs space for its common predecessor and four complete target copies.

**Measured binaries.** Build the two matched Cargo drivers with the instructions in `components/standard-library/guard-stack-evidence.zip` and the two Wild binaries with `components/wild/wild-undefined-evidence.zip`. Install the resulting executables under `$OHM_BENCH_WORK` at the paths below. The baseline uses Cargo `a0c7d08c898d3fdff992f2f431dec57d2486add2`, std `bfa236f639034f61ec884c15bd1f4e0b75e508ac`, Wild `e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11`. The candidate uses Cargo `94c95d6b8ef97b0e63e04b250bc88d1a388a31af`, std `395a878a9ea634f84319d2c04653ec1e79e38f16`, Wild `a77381c04eb7ad9258cdd0475642815a2a1da711`. The `-Zbuild-std` Cargo builds use ThinLTO and one codegen unit.

| Arm | Local executable under `$OHM_BENCH_WORK` | Original SHA-256 |
| --- | --- | --- |
| Baseline Cargo | `path-compare/build/bin/base` | `744843355906004af366ca616a31bde4d79bced59e00355b71eadd7b4257d00c` |
| Candidate Cargo | `path-compare/build/bin/guard-stack` | `42b0c136d6adf60c8bda017451dc847722db0d2304a10af1e3dcf19585e07d52` |
| Baseline Wild | `bin/wild-baseline` | `82a927b86f929b67c58be4d37ab8442f32fcdd115d97334dcc5ac190101d8865` |
| Candidate Wild | `bin/wild-undefined` | `435a253fcd8a44061aa0d88748ca12b8e63a092dc9d42593195142d8071ebc81` |

Both arms compile uv with released `$OHM_TOOLCHAIN_BIN/rustc`, SHA-256 `7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c`. Each Wild link receives `--no-fork` and the inherited jobserver. Record local ELF hashes for a source rebuild, since changing absolute build paths may change the ELF.

**Stage the scripts.** These Bash commands use the environment exports from `first-five.md`. Set `src` to the unpacked directory containing this note and `wild_src` to the unpacked Wild appendix. Use a fresh direct child of the work root so the archived results stay separate.

```bash
set -euo pipefail
W=$OHM_BENCH_WORK B=$OHM_BENCH_ROOT
src=/path/to/unpacked/role-sum-evidence
wild_src=/path/to/unpacked/wild-undefined-evidence
study="$W/tree-count-replay"
install -d -m 700 "$study"/{identical,replica} "$W/edit-link-profile/native-instrument" "$W/dynamorio"
install -m 755 "$src/wrap.py" "$study/wrap.py"
cp "$src"/{calibrate.c,calibrate.py,identical.py,replica.py} "$study/"
cp "$src/identical/summarize.py" "$study/identical/"
cp "$src/replica/qualify.py" "$study/replica/"
cp "$wild_src/native-instrument/count.py" "$W/edit-link-profile/native-instrument/count.py"
drroot=$(dirname "$(dirname "$(realpath "$OHM_DRRUN")")")
test -e "$W/dynamorio/DynamoRIO-Linux-11.3.0-1" || ln -s "$drroot" "$W/dynamorio/DynamoRIO-Linux-11.3.0-1"
printf '%s\n' "$(realpath "$B")" > "$W/bench-home.path"
```

**Warm the seeds.** The primary reads `$W/edit-holdout-cumulative/<endpoint>/protocol.json` with this host's actual source and private Cargo home paths, and `$B/edit-cumulative-<endpoint>/{source,seed-target}`. An existing `replay-first-five.py edit-holdout-cumulative --build --execute` replay already created the targets. Its *local* protocols live under `$B/results/edit-holdout-cumulative`; link that directory at `$W/edit-holdout-cumulative` if absent. For a fresh reproduction, only the following warm phases are needed. The second study's prefix produces separate private fixtures.

```bash
bash "$W/build-drivers.sh" "$W/ohm-cargo" a0c7d08c898d3fdff992f2f431dec57d2486add2 \
  94c95d6b8ef97b0e63e04b250bc88d1a388a31af "$W/bin/cumulative"
warm_fixture() {
  local cohort=$1 ep=$2 seed=$3 mode=$4
  python3 -B "$W/edit_holdout.py" warm "$ep" --study "$cohort" --workspace \
    --result "$W/edit-holdout-$cohort" --cargo-home "$B/cargo-edit-$cohort-$ep" \
    --base "$W/bin/cumulative/parent" --candidate "$W/bin/cumulative/candidate" \
    --seed "$seed" --pairs 8 --mode "$mode"
}
for spec in check:1080811 build:1080812 test:1080813; do
  warm_fixture cumulative "${spec%:*}" "${spec#*:}" dynamorio
done
```

For each endpoint, the counter driver starts from the existing `seed-target`, builds and settles a native structural edit as its own common predecessor, then gives the next identical literal edit to its four native/counted × baseline/candidate copies. Each copy runs at the same visible `$B/edit-<cohort>-<endpoint>/target` path. Preserve every raw native `exec.*` trace, `native-execs.json`, role record and compiler/link roster in the local results.

**Run each registered cohort.** The original affinity was CPUs 16–23. Pick eight allowed CPUs on a different host. Keep the same mask for that endpoint's pilot and samples and retain `-j8`. The harness records and verifies the mask. A rejected or unavailable endpoint has no speed estimate. A first-cohort failure does not suppress another endpoint.

```bash
cpus=$(python3 -c 'import os;print(",".join(map(str,sorted(os.sched_getaffinity(0))[:8])))')
taskset -c "$cpus" python3 -B "$study/calibrate.py" "$study/calibration"
for ep in check build test; do
  if taskset -c "$cpus" python3 -B "$study/identical.py" pilot "$ep"; then
    taskset -c "$cpus" python3 -B "$study/identical.py" samples "$ep" || echo "Inspect $ep rejection" >&2
  fi
done
for spec in check:720931 build:720932 test:720933; do
  ep=${spec%:*}
  if python3 -B "$study/replica/qualify.py" "$study/identical/results/$ep"; then
    warm_fixture cumulative-wall-replica "$ep" "${spec#*:}" wall
    if taskset -c "$cpus" python3 -B "$study/replica.py" pilot "$ep"; then
      taskset -c "$cpus" python3 -B "$study/replica.py" samples "$ep" || echo "Inspect repeat $ep rejection" >&2
    fi
  fi
done
python3 -B "$study/identical/summarize.py"
```

The fresh results are under `$study/{identical,replica}/results`. The independent repeat runs only when the complete first cohort satisfies its registered gate. The original structural-versus-literal exclusion is preserved separately in `summary.md` and `results/exclusions.json`.
