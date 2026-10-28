# Repeat the release-18 depfile experiment

Use an x86-64 Linux host, Bash, Python 3.11+, Git, strace, GNU coreutils and tar, a C/C++ toolchain with Cargo’s normal native build prerequisites and at least 40 GB free. The recorded tools are DynamoRIO 11.3.0 build 1 and Valgrind 3.22.0. The two drivers use the distributed Ohm 1.99.0-18 compiler, static native libraries, ThinLTO, one release codegen unit and matching version metadata. Building Cargo itself uses `-Zohm-defaults=no` and no PGO. Each resulting driver has `ohm-defaults` enabled for the measured uv commands.

In a fresh directory, preserve this layout. `W` contains `measure.py`, `dynamorio/count.py`, a `bin` directory and a `uv` Git repository containing `c22e6b71933443e9cd299d4b6ac8de035ed4825b`. `D` is `W/upstream-monitor/cargo` and contains the recorded Python scripts, plan, `patches/*.patch` and release source archive. Start without previous output directories, driver binaries, or `drivers.json` in `D`. Use a separate empty private `B` for new targets. The archive includes the original plan. Leave its seeds, schedules, declared endpoints and gates intact.

To prepare the fresh runner from `cargo-release18-audit.zip`, extract the evidence separately so the original data stays available for comparison. The optional `finish18.py` invocation below recomputes both analyses directly from the archived rows and logs before any local build. Its `bench-home.path` is needed to load the archived harness.

```bash
set -euo pipefail
replay=$(mktemp -d "${TMPDIR:-/tmp}/ohm-depfile-replay.XXXXXXXX")
unzip -q /path/to/cargo-release18-audit.zip -d "$replay/evidence"
printf '%s\n' "$replay" > "$replay/evidence/work/bench-home.path"
python3 -B "$replay/evidence/work/upstream-monitor/cargo/finish18.py"
W="$replay/work"
D="$W/upstream-monitor/cargo"
I="$replay/evidence/work/upstream-monitor/cargo"
mkdir -p "$D/patches" "$W/dynamorio" "$W/bin"
cp "$replay/evidence/work/measure.py" "$W/"
cp "$replay/evidence/work/dynamorio/count.py" "$W/dynamorio/"
cp "$I"/{build18.py,warm18.py,run18.py,verify-processes18.py,depfile-plan.json,base-7caf399.tar.gz} "$D/"
cp "$I"/patches/*.patch "$D/patches/"
```

```bash
set -euo pipefail
B=$(mktemp -d "${TMPDIR:-/tmp}/ohm-depfile-18.XXXXXXXX")
T="$W/upstream-monitor/toolchain18"
printf '%s\n' "$B" > "$W/bench-home.path"
mkdir -p "$W/bin" "$W/release-like" "$D/patches"
install -d -m 700 "$B/cargo" "$W/release-like/cargo-home"
release=ohm-1.99.0-18
asset="$release-x86_64-unknown-linux-gnu.tar.gz"
# On this devbox, verify the intended OSS identity when invoking gh-auto outside an OSS checkout.
# On another Linux machine use your authenticated gh binary by setting OHM_GH=/absolute/path/to/gh.
OHM_GH=${OHM_GH:-gh-auto}
GH_AUTO_ACCOUNT=oss "$OHM_GH" api user --jq .login
GH_AUTO_ACCOUNT=oss "$OHM_GH" release download "$release" -R astral-sh/ohm -p "$asset" -D "$B"
printf '629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8  %s\n' "$B/$asset" | sha256sum -c -
tar -xzf "$B/$asset" -C "$B"
"$B/rust-1.99.0-dev-x86_64-unknown-linux-gnu/install.sh" --prefix="$T" --disable-ldconfig
export PATH="$T/bin:$PATH" RUSTC="$T/bin/rustc" RUSTDOC="$T/bin/rustdoc"
"$RUSTC" -Vv
"$T/bin/cargo" -Vv
# If the pinned uv repository is absent, populate exactly this object.
git init -q "$W/uv"
git -C "$W/uv" fetch --depth=1 https://github.com/astral-sh/uv.git c22e6b71933443e9cd299d4b6ac8de035ed4825b
git -C "$W/uv" checkout --detach c22e6b71933443e9cd299d4b6ac8de035ed4825b
# Populate the two offline registries in advance. The measured Cargo commands have network access disabled.
CARGO_HOME="$B/cargo" "$T/bin/cargo" fetch --locked --manifest-path "$W/uv/Cargo.toml"
mkdir "$B/driver-fetch"
tar -xzf "$D/base-7caf399.tar.gz" --strip-components=1 -C "$B/driver-fetch"
CARGO_HOME="$W/release-like/cargo-home" "$T/bin/cargo" fetch --locked --manifest-path "$B/driver-fetch/Cargo.toml"
export OHM_DRRUN=/absolute/path/to/DynamoRIO-Linux-11.3.0-1/bin64/drrun
export OHM_VALGRIND="$(command -v valgrind)"
```

The toolchain and input hashes, original 12-pair and 8-pair schedules and driver flags are in `depfile-plan.json`, `depfile-registration.sha256` and `drivers.json` in the results. `base-7caf399.tar.gz` contains the official Cargo commit named in the release manifest. The `patches` directory contains the exact published changes. The matched predecessor applies #264, #267 and #268. The measured candidate adds only #269. The fifth change, #270, is omitted from both arms. [Release manifest](https://github.com/astral-sh/ohm/blob/ohm-1.99.0-18/toolchains/1.99.0/18.json), [published patch](https://github.com/astral-sh/ohm-cargo/pull/269/files)

The original host used CPUs 16–23 for driver builds and 24–27 for the ordinary warm Cargo commands. On another host, choose two disjoint available sets of the same sizes, edit only `build_cpus` and `measurement_cpus` in a replay copy of `depfile-plan.json`, and pass the matching sets below. Keep the original plan and its checksum as the registration. `register.py` describes exactly how its schedules were generated. It creates a new file and is unnecessary when replaying the archived plan.

```bash
taskset -c 16-23 python3 -B "$D/build18.py" & build_job=$!
taskset -c 24-27 python3 -B "$D/warm18.py" & warm_job=$!
wait "$build_job"
wait "$warm_job"
taskset -c 24-27 python3 -B "$D/verify-processes18.py" base
taskset -c 24-27 python3 -B "$D/verify-processes18.py" candidate
taskset -c 24-27 python3 -B "$D/run18.py"
```

Each counter gets its own uv source archive, Cargo home, target and stable visible Cargo executable slot. A native release Cargo build warms each complete uv workspace. Its repeated build must be fresh. The exec admission records every successful `execve`/`execveat` in a fresh native default command in each arm. The depfile admission records successful reads of `target/debug/uv.d`, parks that public file and regenerates it with the same ordinary command. Every public top-level `.d` must remain byte-identical, `Cargo.lock` must stay unchanged and no packages may rebuild. The counted commands use exactly `cargo build`, with the ordinary default job and locking behavior. The counted runs record instructions for the Cargo process across its threads. Neither the native traces nor the forced-regeneration calls contribute samples.

Inspect `admission-*/admitted.json`, `native-exec-*/rosters.json`, the 40 individual sample logs, `count-*/pairs.csv`, and `depfile-results.json`. The gate requires a positive median paired reduction, a positive lower rank confidence bound, two-sided sign p < .05 and two-sided order-balanced randomization p < .05 in each independent cohort. No observations are discarded. Paths, distro tooling and builds can change absolute counts on another machine.
