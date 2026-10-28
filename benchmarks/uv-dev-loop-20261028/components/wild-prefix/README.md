# Reproduce the second ELF section-placement candidate

The parent is Ohm Wild #45 at `a77381c04eb7ad9258cdd0475642815a2a1da711`. `candidate.patch` contains the complete second candidate against that parent. Use the companion `wild-prefix/README.md` to install the original cold-diagnostic wrappers and a pinned uv/toolchain pair, build `parent-wild` and build the first candidate as `wild-prefix/probe-wild`. In a fresh parent checkout, apply this directory's patch and produce the independent third binary.

```sh
git -C "$WILD_SRC" switch --detach a77381c04eb7ad9258cdd0475642815a2a1da711
git -C "$WILD_SRC" apply "$V2/candidate.patch"
(cd "$WILD_SRC" && cargo +1.99.1 build --locked --release -p wild-linker -j4)
cp "$WILD_SRC/target/release/wild" "$V2/v2-wild"
```

Use sibling `wild-prefix`, `wild-prefix-v2` and `edit-link-profile` directories under `$WORK`. `capture.py` rebuilds the seeded private uv checkout after a different equivalent edit in `install_source.rs`, replacing `PathBuf::from(path)` with `PathBuf::from(path.as_os_str())`. It invokes the matched release-source Cargo, shipped rustc and parent linker, saves all five real linker inputs with `WILD_SAVE_BASE`, copies all original emitted binaries and restores the source.

```sh
python3 "$V2/capture.py"
python3 "$V2/canonical.py"
python3 "$V2/pilot.py"
```

`canonical.py` reads the identity from each captured command, creates single-thread parent oracles and records both their hashes and the actual emitted hashes. In this session the outputs agree for all five links. On a fresh machine use the new local oracles because source paths enter debug information. The pilot selects the large uv test harness by unit name. Its three other inputs and expected bytes come from `wild-prefix/fallback`. `pilot.py` checks all three linkers in six differently ordered complete blocks per input. The criterion is recorded under `gate.json`. Replaying the held-out regular executable and smaller test harness belongs to the confirmation stage. Their source, unit names and retained hashes are in `captures/canonical.json`.

The pilot passed the registered rule, so two untouched links and the actual edited command received new confirmation registrations. In a fresh result root use the following commands after the pilot. The scripts intentionally refuse to overwrite original trials.

```sh
python3 "$V2/confirm-links.py" --freeze
python3 "$V2/actual.py" --freeze
taskset -c 24-25 python3 "$V2/confirm-links.py"
taskset -c 24-31 python3 "$V2/actual.py"
python3 "$V2/summarize-links.py"
python3 "$V2/summarize.py" actual
```

The ten-pair link runs each compare the complete file with their local parent oracle. In the real edited commands, both arms run the original `install_source.rs` and its reversed boolean expression with the normal Cargo jobserver. The measurement records every traced Wild process and saves its linked binary by full-file hash. `actual/plan.json` declares the block order, benchmark endpoint and output-parity reporting rule. `actual/samples.csv` and `actual/summary.json` contain the process- and block-level results. On a fresh checkout, confirm all five Cargo unit hash suffixes against the output paths from the first seed before registering the unit manifest.
