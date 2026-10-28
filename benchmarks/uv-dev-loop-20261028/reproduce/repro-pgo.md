# Repeat the profile-guided Cargo comparison

Start with the [Linux toolchain, counter and uv setup](first-five.md). Keep its `run`, `archive`, `OHM_BENCH_ROOT`, `OHM_BENCH_WORK` and `OHM_TOOLCHAIN_BIN` settings. This experiment also needs the published Ohm `rust-src` component and the fixed standard-library patch.

```bash
set -euo pipefail
host=x86_64-unknown-linux-gnu
sysroot="$OHM_BENCH_ROOT/toolchain"
"$run/rust-1.99.0-dev-x86_64-unknown-linux-gnu/install.sh" \
  --prefix="$sysroot" --disable-ldconfig --components=rust-src
unzip -p "$archive/components/standard-library/guard-stack-evidence.zip" \
  std-path-mismatch-guarded.patch > "$run/guard.patch"
echo "ff2dcc74dfc56fb366422c29de08dc1baae4ec4efc91171069358b838177b795  $run/guard.patch" | sha256sum -c -
```

Prepare a private registry seed for the offline builds. Set both Cargo and rustc to the versions under the Ohm sysroot. The two fetches cover the Cargo and standard-library lockfiles.

```bash
base=a0c7d08c898d3fdff992f2f431dec57d2486add2
install -d -m 700 "$run/cargo-fetch" "$run/pgo-seed"
git -C "$OHM_BENCH_WORK/ohm-cargo" archive "$base" | tar -x -C "$run/cargo-fetch"
for manifest in "$run/cargo-fetch/Cargo.toml" "$sysroot/lib/rustlib/src/rust/library/Cargo.toml"; do
  env -u CARGO_NET_OFFLINE RUSTC="$OHM_TOOLCHAIN_BIN/rustc" CARGO_HOME="$run/pgo-seed" \
    "$OHM_TOOLCHAIN_BIN/cargo" fetch --locked --target "$host" --manifest-path "$manifest"
done
```

Provision the pinned upstream training inputs. On this devbox the script can read GitHub through `gh-auto`. On another host, supply `--perf-repo /path/to/rustc-perf` with a Git object store containing commit `0a054b0ead56e41a4584bfab6fdc1a5fad2aedc3`. That option reads the two exact Git trees locally. The LLVM tool archive is verified against its pinned SHA-256.

```bash
recipe="$OHM_BENCH_WORK/pgo-holdout"
stable_lib="$(rustup run 1.99.1 rustc --print sysroot)/lib"
GH_AUTO_ACCOUNT=oss python3 -B "$recipe/provision.py" "$run/pgo-materials" \
  --oss-repo "$OHM_BENCH_WORK/ohm-cargo" --stable-lib "$stable_lib"
env -u CARGO_NET_OFFLINE python3 -B "$recipe/run.py" \
  --scratch "$run/pgo-build" --materials "$run/pgo-materials" \
  --cargo-repo "$OHM_BENCH_WORK/ohm-cargo" --toolchain "$sysroot" \
  --std-patch "$run/guard.patch" --seed-home "$run/pgo-seed" --arms base guard-stack --jobs 8
```

The build first verifies the full profile-generation and profile-use cycle on a small binary, with an instrumented target and uninstrumented std. It then performs both Cargo cycles. Each source arm trains its instrumented driver on the pinned bitmaps and Diesel workloads. The final executables are under `pgo-build/bin`. To replay the two matched comparisons, use distinct checkout, cache and target paths. The original short and long uv checkouts had UTF-8 path lengths of 28 and 76 bytes. Path length affects the standard-library result.

```bash
cp -a "$OHM_BENCH_ROOT/cargo" "$OHM_BENCH_ROOT/pgo-short-home"
cp -a "$OHM_BENCH_ROOT/cargo" "$OHM_BENCH_ROOT/pgo-long-home"
pair=(--base "$run/pgo-build/bin/base" --candidate "$run/pgo-build/bin/guard-stack" --settle-counter)
python3 -B "$OHM_BENCH_WORK/measure.py" "${pair[@]}" --mode dynamorio --pairs 12 --seed 611390 \
  --source "$OHM_BENCH_ROOT/u" --cargo-home "$OHM_BENCH_ROOT/pgo-short-home" \
  --target pgo-short --result "$run/pgo-confirm" --endpoints check build test
python3 -B "$OHM_BENCH_WORK/measure.py" "${pair[@]}" --mode instructions --pairs 8 --seed 611391 \
  --source "$OHM_BENCH_WORK/uv" --cargo-home "$OHM_BENCH_ROOT/pgo-long-home" \
  --target pgo-long --result "$run/pgo-replica" --endpoints test build check
```

The separate downloaded-binary comparisons use the shipped `cargo` as `--base`, and either retrained executable as `--candidate`. See [the recorded measurement commands](measure-pgo-drivers.sh) for the fixed arm seeds, sample counts and order.
