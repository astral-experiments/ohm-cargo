# Cargo build after an edit to uv on Ohm -18

The original eight patches reduced instructions for a complete workspace `cargo build --locked --offline -j8` after a real edit in `crates/uv/src/install_source.rs`. The two checkouts used separately scheduled edits and randomized pairs.

| Raw evidence | Matched base | Historical patches | Paired median reduction | 99.22% median interval | Pairs improved |
| --- | ---: | ---: | ---: | --- | ---: |
| [Initial](initial.zip) | 15.2533B | 14.8821B | 2.434% | 2.233% to 2.513% | 8/8 |
| [Replica](replica.zip) | 15.2560B | 14.8788B | 2.441% | 2.216% to 2.541% | 8/8 |

The two-sided sign test gave p = .0078125 and the balanced-order randomization test gave p = .02857 in each checkout. Arm columns show separate medians. The reduction and interval use paired command totals.

Each build invoked one Cargo, three rustc processes and two Wild linkers. The counter sums application instructions in those processes and their threads. Both arms used the distributed -18 rustc. The treatment bundled five Cargo patches, one standard-library patch linked into Cargo and the two original Wild patches. GCC, collect2, observer, pre-exec and kernel instructions lie outside this count. Elapsed times in the separate ordinary full-toolchain runs were inconclusive. [Ordinary build, check and test timings](../full-toolchain-wall/)

Extract each packet into its own empty directory and run `python3 -I -B replay.py`. Both packets retain the initial failed product admission and the subsequent stock ELF calibration. The first cohort also records the resource handoff after its first accepted pair. The replays check the measured roster, edits, product hashes, original schedules and statistics. Large calibrated executable bytes are retained on the benchmark host.
