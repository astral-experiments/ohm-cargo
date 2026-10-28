# Repeat the five Cargo instruction comparisons

Use x86-64 Linux, Python 3.11 or newer, Git, rustup, GNU coreutils and tar, a native C/C++ toolchain with the Cargo build dependencies, and Cachegrind. The measurements used Valgrind 3.22.0. Commands below assume Bash and a fresh location. Preparing six Cargo drivers and both edited test-target copies can use tens of gigabytes. The recorded individual package sets, binary and source hashes, and arm order are in the archive.

```bash
set -euo pipefail
run=$(mktemp -d "${TMPDIR:-/tmp}/ohm-replay.XXXXXXXX")
archive="$run/archive"
mkdir -m 700 "$archive"
unzip -q /path/to/uv-ohm-benchmarks.zip -d "$archive"
export OHM_BENCH_WORK="$archive/reproduce" OHM_BENCH_ROOT="$run/bench"
install -d -m 700 "$OHM_BENCH_ROOT" "$OHM_BENCH_ROOT/cargo"
export OHM_TOOLCHAIN_BIN="$OHM_BENCH_ROOT/toolchain/bin"
export OHM_VALGRIND="$(command -v valgrind)"
rustup toolchain install 1.99.1 --profile minimal
git clone https://github.com/astral-sh/ohm-cargo.git "$OHM_BENCH_WORK/ohm-cargo"
git -C "$OHM_BENCH_WORK/ohm-cargo" fetch origin refs/pull/270/head
while IFS= read -r sha; do git -C "$OHM_BENCH_WORK/ohm-cargo" cat-file -e "$sha^{commit}"; done \
  < <(awk -F '\t' 'NR>1 {print $3}' "$archive/release-build/published-identities.tsv")
uv_sha=c22e6b71933443e9cd299d4b6ac8de035ed4825b
git clone https://github.com/astral-sh/uv.git "$OHM_BENCH_WORK/uv"
git -C "$OHM_BENCH_WORK/uv" checkout --detach "$uv_sha"
git clone --no-checkout "$OHM_BENCH_WORK/uv" "$OHM_BENCH_ROOT/u"
git -C "$OHM_BENCH_ROOT/u" checkout --detach "$uv_sha"
```

The release installer assembles the toolchain from per-component trees inside its tarball. The raw archive's top directory is an installer distribution. Its required Cargo, rustc, standard library and bundled Wild are available after installation.

```bash
cd "$run"
ohm=ohm-1.99.0-17-x86_64-unknown-linux-gnu.tar.gz
curl -fL -o "$ohm" "https://labs.astral.sh/ohm/releases/ohm-1.99.0-17/$ohm"
echo "163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572  $ohm" | sha256sum -c -
tar -xzf "$ohm"
./rust-1.99.0-dev-x86_64-unknown-linux-gnu/install.sh \
  --prefix="$OHM_BENCH_ROOT/toolchain" --disable-ldconfig \
  --components=rustc,rust-std-x86_64-unknown-linux-gnu,cargo
dr=DynamoRIO-Linux-11.3.0.tar.gz
curl -fL -o "$dr" "https://github.com/DynamoRIO/dynamorio/releases/download/release_11.3.0-1/$dr"
echo "ae02049df5c4daeb82d4087aaa0d38bf58cdd26b38fb6042dccf27cbc32ceed9  $dr" | sha256sum -c -
tar -xzf "$dr"
export OHM_DRRUN="$run/DynamoRIO-Linux-11.3.0-1/bin64/drrun"
"$OHM_TOOLCHAIN_BIN/rustc" -Vv
"$OHM_VALGRIND" --version
(cd "$OHM_BENCH_WORK/uv" && PATH="$OHM_TOOLCHAIN_BIN:$PATH" \
   CARGO_HOME="$OHM_BENCH_ROOT/cargo" "$OHM_TOOLCHAIN_BIN/cargo" fetch --locked)
```

Use the same filesystem for the scripts' binary directory and the benchmark root. Both samplers switch the executable using a hard link. The canonical Cargo-home path must have ancestors owned by the user or root and no group/world-write bit, except root-owned sticky directories such as `/tmp`. After warming, verify `$OHM_BENCH_ROOT/cargo/.ohm-registry-json-v2` exists and contains files. An untrusted ancestor silently disables that cache. The private prefix above satisfies the rule on a standard Linux system.

The helper reads the archived parent and head revisions, command order, number of pairs, random seed, counter and source layout. Invoke the helper without `--execute` to print the commands. Measured output goes to `$OHM_BENCH_ROOT/results`. The primary uses DynamoRIO and 12 pairs, and the replication uses Cachegrind and eight pairs on a separately warmed target. For the source-build replication, both binaries use stable rustc 1.99.1. Keep rustup's cargo first on the build-driver PATH. The Ohm rustc installed above builds uv in every comparison.

```bash
cd "$archive"
helper="$OHM_BENCH_WORK/replay-first-five.py"
for stage in unit warnings feature depfile semver; do
  python3 -B "$helper" "$stage-confirm" --build --execute
  python3 -B "$helper" "$stage-replica" --execute
done
python3 -B "$helper" cumulative-confirm --build --execute
python3 -B "$helper" edit-holdout-unit --execute
python3 -B "$helper" edit-holdout-cumulative --execute
```

An unchanged measurement aborts on unexpected Cargo or rustc work. On a host where instrumentation first changes Cargo's view of the inputs, use a fresh benchmark root and append `--settle-counter` to the unchanged-workspace commands. This adds four unreported warmups under that counter and verifies freshness on the last two. The additional prewarming is recorded in the new protocol. The observed path lengths and installed libraries can affect the precise reductions. Each pair must see the same absolute source, executable and target paths.

## Ohm-built release-style replication

Build these six drivers separately with the shipped Ohm rustc, ThinLTO, one codegen unit and static libraries. Start with a fresh lab alongside the installed `toolchain/`. The archived patches already contain all five proposed changes.

```bash
lab="$OHM_BENCH_ROOT/release-build"
export OHM_RELEASE_BINS="$lab/bin"
repo="$OHM_BENCH_WORK/ohm-cargo"
base=a0c7d08c898d3fdff992f2f431dec57d2486add2
mkdir -p "$lab"/{src,bin,logs,cargo-home}
cp -a "$archive/release-build/patches" "$lab/"
cp "$archive/release-build/"{build-one.sh,build-rest.sh,build-semver.sh,source-lock.sha256,patches.sha256,affected-files.txt} "$lab/"
(cd "$lab" && sha256sum -c patches.sha256)
git -C "$repo" archive "$base" | tar -xf - -C "$lab/src"
git -C "$repo" show -s --format='%H%n%h%n%cs' --abbrev=9 "$base" > "$lab/src/git-commit-info"
(cd "$lab/src" && sha256sum -c "$lab/source-lock.sha256")
(cd "$lab/src" && xargs -d '\n' sha256sum < "$lab/affected-files.txt" > "$lab/logs/base.source.sha256")
bash "$lab/build-one.sh" base
bash "$lab/build-rest.sh"
bash "$lab/build-semver.sh"
for stage in unit warnings feature depfile semver; do
  python3 -B "$helper" "$stage-release-like" --execute
done
```

The first release-style build fetches its dependencies. Subsequent builds use the accumulated cache offline. The release-style replication needs the Ohm distribution's compiler and the archived five Cargo patches. The distribution's PGO training profile was unavailable. On failure, preserve the logs and use a fresh output/study location for the next run. The samplers reject overwriting an existing series.
