# Storage for the full Ruff CLI with branch retention enabled

On the draft compiler, one switch from the original Ruff branch to the feature added 495.6 MiB (+20.55%). Returning to the original branch added 49.4 MiB (+1.97%). Returning to the feature added 264.9 MiB (+11.49%), which remained after the next unchanged build. Without the opt-in flag, rustc keeps its usual single session. This experiment used one independent installation per setting and two additional empty builds. [Complete census and rerun](census)

| Whole Cargo target and build directories | Default | Opt-in | Difference |
| --- | ---: | ---: | ---: |
| First feature visit | 2,411.3 MiB | 2,906.8 MiB | +495.6 MiB |
| Return to original branch | 2,514.0 MiB | 2,563.5 MiB | +49.4 MiB |
| Return to feature and next unchanged build | 2,305.9 MiB | 2,570.7 MiB | +264.9 MiB |
| Largest sampled allocation across the history | 2,837.2 MiB | 3,123.5 MiB | +286.4 MiB |

Every row counts physical blocks across both directories and counts hard links once. The largest sampled allocation is a lower bound for each setting. There were 190,617 samples, nominally 10 ms apart, with a longest gap of 419 ms. The final incremental files alone grew from 1,039.2 to 1,304.0 MiB. [Sampler and per-visit file data](census/storage.json)

Native objects added 174.2 MiB, including 90.1 MiB from `ruff_linter`. Rust metadata added 36.2 MiB. The two large incremental tables in raw and packed form together added 49.6 MiB. The remaining files added about 4.8 MiB. The physical census measured distinct inodes. Determining whether two distinct inodes contain the same object would require comparing their contents. [Per-crate object and metadata breakdown](by-crate)

All 12 ordinary Cargo commands produced the expected CLI and linked reader. Both branch returns matched the entire independently clean executable for their own option. Across options, every executable section matched. The differences in the full ELF were confined to the build ID and debug data for Cargo’s actual jemalloc build path. The decoder compared both entire debug streams after substituting that path. Neither the census nor this native comparison measured elapsed speedup. [Native comparison](native) · [Separate timing protocol](../full-cli-timing/registration)

Of the 174.2 MiB of extra object files, at most 76.43 MiB could match an existing whole object by length. The cache already shares 889 A/B object pairs through hard links. We cannot assign any actual recoverable byte count without the object contents. [File-length bounds and existing sharing](object-dedup-bound)

Run `python3 -IB verify.py` here to reopen the sample streams, recompute the file classes, replay the negative controls and reconcile all four clean binaries with the native comparison. The census contains the source-history replay command.
