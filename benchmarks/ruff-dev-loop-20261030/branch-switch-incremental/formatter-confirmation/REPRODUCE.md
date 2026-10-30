# Repeating the formatter experiment

The offline verifier requires Python 3.11 or newer. It checks every published observation, rebuilds the statistics, and separately enumerates the 924 balanced assignments using bit masks. Six corrupted observations exercise the workload, storage, source, diagnostic and clock guards.

```sh
python3 -IB verify.py
```

A fresh compilation run requires x86-64 Linux, GNU cp, Git, Rustup proxies, GCC, and two matched complete Ohm SDKs. The campaign used optimized rustc sources 7e71d3150938ff8ed82aca03416439d7e5b87ef3 and 6b7f424ece4bc978ead5546b73e1b31d5ccb1e70, one common Cargo built from 2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c, and one stock Wild. The physical Rust/standard-library files are enumerated in materials.json. Use a separate prepopulated Cargo home that can resolve the common Ruff lockfile offline. Four available logical CPUs and room for the SDK, registry copy, source and incremental target are required. Each visit records its complete compiler and Cargo identities.

Here is a single fresh ordinary history on the candidate. Set the four paths and CPU IDs for the machine running it. Both output paths must start absent. The Git input is read-only and must contain both #28335 commits. The runner preserves the new workspace and every stdout/stderr for inspection.

```sh
export RUFF_CHECKOUT=/path/to/ruff
export CARGO_OFFLINE_HOME=/path/to/prepopulated-cargo-home
export PARENT_SDK=/path/to/parent-sdk
export CANDIDATE_SDK=/path/to/guarded-sdk
export STUDY_BASE=/absolute/path/to/new-study
export CPU_SET=0-3
mkdir -m 700 "$STUDY_BASE"
mkdir "$STUDY_BASE/reports" "$STUDY_BASE/preserved"
taskset -c "$CPU_SET" python3 -IB replay_one.py \
  --sdk "$CANDIDATE_SDK" --ruff-checkout "$RUFF_CHECKOUT" \
  --cargo-home "$CARGO_OFFLINE_HOME" --work "$STUDY_BASE/work" \
  --out "$STUDY_BASE/reports/example" --mode history --min-free-gib 8
mv -- "$STUDY_BASE/work" "$STUDY_BASE/preserved/example"
```

The following commands reproduce the registered order with the same logical workspace path on every visit. They retain all generated directories, so allow sufficient storage for 28 copies of the SDK, registry and work. An isolated, fresh RAM mount per visit can provide the same paths while retaining only the verified reports and both reference ELFs externally. The campaign ran one such mount at a time. Keep these new measurements separate from the recorded confirmation.

```sh
python3 -IB - <<'PY' > "$STUDY_BASE/order.tsv"
import json
for slot in json.load(open("schedule.json"))["order"]:
    print(slot, slot[-1], "controls" if slot.startswith(("admit-", "post-")) else "history")
PY
while read -r slot arm mode
do
  case "$arm" in P) sdk="$PARENT_SDK" ;; Q) sdk="$CANDIDATE_SDK" ;; esac
  if [ "$mode" = controls ]; then set -- --trace-returns; else set --; fi
  taskset -c "$CPU_SET" python3 -IB replay_one.py \
    --sdk "$sdk" --ruff-checkout "$RUFF_CHECKOUT" \
    --cargo-home "$CARGO_OFFLINE_HOME" --work "$STUDY_BASE/work" \
    --out "$STUDY_BASE/reports/$slot" --mode "$mode" --min-free-gib 8 "$@" || exit 1
  mv -- "$STUDY_BASE/work" "$STUDY_BASE/preserved/$slot" || exit 1
done < "$STUDY_BASE/order.tsv"
python3 -IB analyze_replay.py "$STUDY_BASE/reports" schedule.json > "$STUDY_BASE/replication.json"
```

The optional --trace-returns argument requires strace and preserves all raw per-thread exec/open streams on the two unscored branch returns. Each routine timed command runs untraced. The campaign collector additionally took physical hardlink-deduplicated storage inventories after each successful phase and traced all seven commands in its four separate control installations. The public command above is an independent local rerun of the same source, toolchain, Cargo entry point, and behavioral guards. Each newly populated SDK or checkout path can change its cross-machine ELF hash. Compare the two local matching revisions against their own local clean builds.

The original acquisition has separately retained per-command JSON streams, complete test executables, compressed inode ledgers and all per-thread strace files. Given that original private raw root, the full readers can regenerate the public projection without a build.

```sh
python3 -IB raw/readback.py "$RAW" > reacquired.json
gzip -dc observations.json.gz > published.json
cmp reacquired.json published.json
python3 -IB analyze.py reacquired.json schedule.json > recomputed.json
cmp recomputed.json statistics.json
```
