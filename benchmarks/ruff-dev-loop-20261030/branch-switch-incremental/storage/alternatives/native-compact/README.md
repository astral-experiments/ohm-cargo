# Compact incremental tables in rustc

On Unix, this experimental compiler stores the dependency graph and query cache in compressed form after it detects another checkout. The two tables account for most of the additional branch history. The default remains one uncompressed session. Each packed table carries an identity, size and checksum. Rustc validates both before installing the restored files into its private write session. A corrupt packed table triggers a fresh build. [Source patch against Ohm Rust #274](compiler.patch) · [Rebuilt SDK, tests and identities](compiler.json)

The benchmark switches between the two real Ruff commits linked in the main study and builds `ruff_python_parser`. Both sides ran the same physical compiler, standard library, Cargo and Wild on ext4 with separate, initially empty target and build directories. Off enables the ordinary single session. On enables two sessions and compression. Four independent clean references, a rejected source edit and its repair validate the outputs. The disk figures include the complete allocated target and build directories after the command, deduplicated by inode. They exclude temporary high-water usage while rustc is running.

## 12 fresh pairs

Six pairs ran each order. The intervals give simultaneous 95% coverage for the two return directions. The predeclared thresholds required both lower bounds to exceed 2× and every complete return to fit within 10% of its control.

| Visit | Off median | On median | Paired speedup | Range or interval | Whole storage, off → on |
| --- | ---: | ---: | ---: | ---: | ---: |
| First feature visit | 8.71 s | 9.04 s | 0.96× | — | 273 → 324 MiB |
| Return to parent | 9.00 s | 2.92 s | 3.05× | 2.93–3.14× | 288 → 280 MiB |
| Return to feature | 9.10 s | 3.56 s | 2.51× | 2.44–2.64× | 258 → 281 MiB |
| First feature visit plus return | 17.75 s | 11.99 s | 1.48× | — | — |

The registered comparison met its two thresholds. The largest settled increase in any measured return was 8.8%.

[Complete observations](sample-build-12-pairs-elapsed-202610300711.json.gz) · [Independent native and disk readback](native-build-12-pairs-elapsed-202610300711.json.gz) · [Paired calculations](summary-build-12-pairs-elapsed-202610300711.json)

## 2 fresh pairs

The two directions used mirrored installation orders. The range shows the two observations.

| Visit | Off median | On median | Paired speedup | Range or interval | Whole storage, off → on |
| --- | ---: | ---: | ---: | ---: | ---: |
| First feature visit | 8.59 s | 8.84 s | 0.97× | — | 273 → 323 MiB |
| Return to parent | 8.61 s | 2.87 s | 3.00× | 2.98–3.02× | 288 → 279 MiB |
| Return to feature | 8.70 s | 3.37 s | 2.59× | 2.58–2.59× | 258 → 281 MiB |
| First feature visit plus return | 17.20 s | 11.71 s | 1.47× | — | — |

[Complete observations](sample-build-2-pairs-elapsed-202610300704.json.gz) · [Independent native and disk readback](native-build-2-pairs-elapsed-202610300704.json.gz) · [Paired calculations](summary-build-2-pairs-elapsed-202610300704.json)

## Edits after a branch switch

A second experiment kept retention enabled on both compilers and compared raw files against the integrated codec. After visiting both branches, reversing and restoring a real Ruff grammar edit took an average of 2.680 s with raw files and 3.064 s with compression. The compact compiler added 0.387 and 0.380 s per dirty edit in the two fresh, mirrored blocks. It saved 99 MiB when the feature branch had settled after editing. Both compilers produced the clean-matching runnable reader and the native object contents for all source states. [Ordinary edits, per-block costs and native readbacks](grammar-edits)

## Reproduce

Apply `compiler.patch` to `c9119d267c9843f0fb5dcbc1cc05653eac6051e3` in Ohm Rust. The resulting Git tree is `b5b25bc034777b3017adc8d7201acf6d39e0c219`. Its separately bootstrapped 55-file native SDK matched the measured compiler byte for byte. Build an optimized toolchain and use the same physical installation for both roles. One example from the branch-switch benchmark directory is

```sh
python3 -IB opt-in/run.py --parent-sdk "$SDK" --candidate-sdk "$SDK" \
  --same-sdk --enable-retention --workflow build --pairs 12 --jobs 4 \
  --order-seed 202610300711 --offline --pack "$RUFF_PACK" --out "$NEW_OUTPUT"
```

From this directory, `python3 -IB verify.py` reopens both readbacks and recomputes the paired speedups, intervals and storage ratios. `python3 -IB grammar-edits/verify.py` checks the ordinary edits separately.

## Complete Ruff executable

One separate installation per option built the entire Ruff CLI through the same five visits. The first feature build used 495 MiB more with retention enabled (+20.5%). The returns used 49 MiB (+1.9%) and 265 MiB (+11.5%) more. The highest observed allocation over the five commands increased by 286 MiB (+10.1%). The warmed feature executable matched an independently empty build byte for byte in each setting. This study measures disk usage. [All visits, sampled allocation and native file checks](full-ruff-cli)
