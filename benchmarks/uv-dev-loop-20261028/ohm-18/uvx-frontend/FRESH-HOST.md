# Collect new compiler timings

The registered runs contain machine-local SDK, checkout, target and incremental-cache paths. `portable.py` only rescores those measurements. `fresh.py` captures comparable arguments from the actual Cargo/rustc/Wild processes on a separate Linux x86-64 computer, then runs the same three compiler roles, genuine edit substitutions, bank switching, process/token observer, admission and 48-pair schedules. Its results have their own paths and provenance. `fresh-selftest.py` verifies the helper's parsing and relocation against all six original real vectors and twelve measured arm vectors. A new host timing run is external to this packet verification.

Use a quiet, dedicated Linux host with sixteen available logical CPUs, GNU/Linux build tools appropriate for uv, strace, git, Python 3.12 and NumPy. Reserve space for two independent, complete warm `uv` debug and test-preparation targets. Preloading network dependencies is outside every timer. Verify that your installed Ohm is the release prefix itself. The hash check covers the exact official executable files for Cargo, rustc and the packaged Wild ELF at `lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd`. Cargo's source is `7caf39914da1e28a67744ecbc963a5f26361474d`. The release manifest carries its matching compiler pin. [Ohm 1.99.0-18](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-18)

From the extracted evidence directory, set `RUN` to a new, disposable path outside this packet and the recorded host's working and benchmark directories. Define `OHM` as the full installed release prefix and `CACHE` as an initially clean Cargo home. Keep the two checkout lengths distinct. Use the same sixteen logical CPUs for every command and quiet the rest of the host.

```sh
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
RUN=/large-volume/ohm-small-bin-reproduction
OHM=/opt/ohm-1.99.0-18
CACHE="$RUN/cargo-home"
UV=c22e6b71933443e9cd299d4b6ac8de035ed4825b
A="$RUN/a"
B="$RUN/independent/longer-checkout-b"
mkdir -p "$A" "$B" "$CACHE"
git clone https://github.com/astral-sh/uv "$A/uv"
git -C "$A/uv" checkout --detach "$UV"
git clone --no-local "$A/uv" "$B/uv"
git -C "$B/uv" checkout --detach "$UV"
CARGO_HOME="$CACHE" RUSTC="$OHM/bin/rustc" "$OHM/bin/cargo" fetch --locked --manifest-path "$A/uv/Cargo.toml"
taskset -c 0-15 python3 fresh.py capture --cohort initial --root "$A" --toolchain "$OHM" --cargo-home "$CACHE"
taskset -c 0-15 python3 fresh.py capture --cohort replica --root "$B" --toolchain "$OHM" --cargo-home "$CACHE"
taskset -c 0-15 python3 fresh.py replay --cohort initial --root "$A" --toolchain "$OHM"
taskset -c 0-15 python3 fresh.py replay --cohort replica --root "$B" --toolchain "$OHM"
```

Capture uses the pinned workspace's default Cargo selection. Each independently warmed checkout first runs `cargo build --locked --offline -j8` and `cargo test --no-run --locked --offline -j8`. Before recapturing each command it writes a genuine tagged edit to the one uvx Rust input and runs the command with `-vv` under `strace -ff -qq -s 2048 -e trace=execve,execveat`. Cargo's verbose lines make the targets recognizable. The successful kernel `execve` vectors supply the actual argument boundaries. A real named eight-thread uvx compile and a real packaged Wild execution are required. The normal build must emit exactly one uvx binary compiler invocation. Test preparation must emit both the ordinary binary and its separate `--test` harness.

The fresh helper preserves the pristine source bytes, original nanosecond time and lockfile, then parks each completed dependency donor at `r18-four/shipped` under its private root. The included unmodified relocation function redirects the actual locked extern and native search paths to that donor. It requires each file or directory to exist. It maps every output, incremental and temporary path to the same visible path, backed by independent writable banks for eight and one threads. Unexpected target paths fail admission. The two arm argument vectors differ solely by a final `-Zthreads=1` immediately following Ohm's `-Zthreads=8`.

The initial source edit includes the current five-character tag in the error printed when the adjacent uv executable is missing. The replica changes the recognized executable-name prefix to `uvx-<tag>`. Fresh replays build only this real source file against released-Cargo-produced dependencies. They retain all 48 fixed pairs in each checkout and role, original run positions, exact argv, plain compiler logs, foreground elapsed, CPU usage, permit counts and final process inventory. The dedicated host must be idle before each batch. No outlier is removed. A fresh compiler fail, invalid process/token closure or product mismatch stops that attempt.

Admission and postflight compare raw ELF SHA-256, size and raw depfile bytes across the two thread counts. They invoke the current normal binary outside the timer to verify either the exact tagged missing-sibling diagnostic and exit 2 or the tagged executable selecting its `uv@probe` sibling and forwarding `tool uvx fixed-argument`. The harness only lists its zero test cases. No test payload runs. Each `fresh-replay/done.json` reports the same per-role paired statistics and native gate. Require the same role to clear both independent checkouts and inspect the prespecified material-loss veto as documented in the frozen score. Runtime behavior, file layout, host release, affinitized CPUs, and package-selection differences should be recorded with any new result. For complete commands, the paired raw foreground Cargo comparison is a separate study.
