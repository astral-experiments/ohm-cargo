# Reproduce the ELF section-placement experiment

The parent is Ohm Wild #45 at `a77381c04eb7ad9258cdd0475642815a2a1da711`. This study builds the parent and `candidate.patch` with stock Rust 1.99.1 on x86-64 Linux. `regression-test.patch` is the separate test-only change.

Use a disposable checkout and the same source path for each build. Set `STUDY` to this evidence directory and `WILD_SRC` to the checkout.

```sh
git -C "$WILD_SRC" switch --detach a77381c04eb7ad9258cdd0475642815a2a1da711
(cd "$WILD_SRC" && cargo +1.99.1 build --locked --release -p wild-linker -j4)
cp "$WILD_SRC/target/release/wild" "$STUDY/parent-wild"
git -C "$WILD_SRC" apply "$STUDY/candidate.patch"
(cd "$WILD_SRC" && cargo +1.99.1 build --locked --release -p wild-linker -j4)
cp "$WILD_SRC/target/release/wild" "$STUDY/probe-wild"
```

The companion `wild-link-benchmarks.zip` supplies the original cold-diagnostic experiment's `run`, `native-instrument/tool/cc`, `native-instrument/linker/ld.bfd`, `native-instrument/count.py` and `native-instrument/toggle`. Arrange these under `$WORK/edit-link-profile`, use `$WORK/toolchain` for the complete Linux Ohm 1.99.0-17 release and `$WORK/dynamorio` for 11.3.0-1 plus the shared `count.py`. The scripts use `$WORK/edit-link-profile/uv` and a private `target`. Check out uv at `c22e6b71933443e9cd299d4b6ac8de035ed4825b` and populate its locked dependencies in `$WORK/cargohome` before offline runs.

The edited-command receipt used `$WORK/bin/matched-base`, Cargo rebuilt from release revision `a0c7d08c898d3fdff992f2f431dec57d2486add2`, and shipped rustc `bfa236f639034f61ec884c15bd1f4e0b75e508ac`. Their executable hashes are under `actual/executables-sha256.txt`. Keep Cargo, rustc, the target and the checked-out source paths fixed across arms. Seed with `cargo test --no-run --locked --offline -j4`.

For fresh linker inputs, run the equivalent edit in the companion `native-instrument/toggle`, set `WILD_SAVE_BASE=$WORK/edit-link-profile/captured/inputs` for that invocation only and rebuild. The linker writes five numbered `run-with` scripts. Identify the unit from the first direct `*.rlink-objects` directory in each script because the capture numbers depend on scheduling. Run each script with the parent and stash its local byte oracle before measuring. The 305 MiB uv executable was capture 3 in this study, and the large and small test harnesses were captures 0 and 2.

```sh
OUT="$STUDY/oracle" "$CAPTURE/run-with" "$STUDY/parent-wild" -- \
  --dynamic-linker /lib64/ld-linux-x86-64.so.2 --threads=1 --no-fork
OUT="$STUDY/output" "$CAPTURE/run-with" python3 -B "$WORK/dynamorio/count.py" -- \
  "$STUDY/probe-wild" -- --dynamic-linker /lib64/ld-linux-x86-64.so.2 --threads=1 --no-fork
cmp "$STUDY/oracle" "$STUDY/output"
```

The explicit interpreter restores the path changed by the save directory. Compare each build to the local oracle since absolute source paths enter Rust debug information. `replay.py` implements the registered balanced pairs and checks every output. `actual.py --freeze` writes the separate edited-command plan in a fresh result directory, and `actual.py` runs the 32 real commands with the default jobserver and accounts for all five Wild children. `compare-artifacts.py` groups the retained complete outputs by unit and edit. `fixtures.py` exercises malformed names, default and custom layouts, partial linking and diagnostics. The `fallback` directory contains the three additional real-input controls and their raw counts.

For the three fallback controls, `fallback/prepare.sh` reconstructs the selected regex-syntax object and the parent oracles. `UV_CLIENT_RLIB` can point at the uv-client archive emitted by a fresh checkout. If Cargo produces different unit suffixes, record those names and update the local input and unit manifest before registering the new experiment. The original immutable trial files retain their own unit IDs.
