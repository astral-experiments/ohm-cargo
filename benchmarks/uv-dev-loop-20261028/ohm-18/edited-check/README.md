# Release-18 edited uv check

Both arms set `RUSTC_WRAPPER`. On these marker-bearing targets, that disables two check-mode reuse paths in release Cargo. The numbers below apply to the observed configuration. [Source conditions, launch evidence and fixture fingerprints](../observer-audit/README.md)

Both cohorts ran full-workspace `cargo check --locked --offline -j8` after changing the private Homebrew path predicate in `crates/uv/src/install_source.rs`. The structural edit accepted an additional `uv-preview-A00` or `uv-preview-J00` directory name. Each subsequent edit changed only the two decimal digits. Each pair used the same edit bytes, mtime, visible paths and predecessor history. The initial and replica fixtures used independent roots, schedules and literals. The original and every exact edit are in `inputs/`.

The control used matched, separately trained release-18 PGO Cargo. The treatment used the five Cargo changes and the guarded standard-library path comparison linked into Cargo. Each compile used the same distributed release-18 rustc. Both stacks selected their corresponding Wild executable. Every admitted and held-out check ran exactly one Cargo process and one rustc process, rebuilt only the uv library and emitted byte-identical metadata across arms for each edit. No Wild or tests ran.

| Cohort | Base instructions | Candidate instructions | Paired reduction | Exact 99.22% rank interval | Wins | Sign p | Balanced-order p |
|---|---:|---:|---:|---:|---:|---:|---:|
| initial | 5.006226B | 4.982587B | 0.4722% | 0.4458% to 0.4793% | 8/8 | 0.0078125 | 0.028571429 |
| replica | 5.004709B | 4.980658B | 0.4728% | 0.4210% to 0.4952% | 8/8 | 0.0078125 | 0.028571429 |

The registered primary gate required a positive initial rank interval, two-sided sign p below .05/3 and an exact balanced-order p below .05. The independent repetition required a positive median and both two-sided p values below .05. Both cohorts passed.

The counters sum dynamic application instructions from all threads in Cargo and every invoked rustc and Wild. Kernel instructions, pre-exec child work and launchers lie outside the metric. Native elapsed time is a separate experiment.

| Cohort | Control Cargo share | Control rustc share |
|---|---:|---:|
| initial | 16.840% | 83.160% |
| replica | 16.824% | 83.176% |

From the root of an extracted copy, run the following commands using Python 3.11 or later. The scorer re-joins each scheduled assignment with per-process and per-thread receipts, checks the native and instrumented rosters and output hashes, then recalculates both gates. The CSV lists one row per held-out command and points to each raw PID receipt. The frozen plan also includes schedules for the separately collected endpoints. This packet includes only the completed check observations.

```sh
sha256sum -c work/round18-cargo/edited-check/SHA256SUMS
python3 -I -B work/round18-cargo/edited-check/score.py
```
