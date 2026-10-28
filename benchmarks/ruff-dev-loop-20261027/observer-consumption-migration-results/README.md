# Correct a poisoned -17 target by replacing Cargo

The starting states are six real targets made by the published Ohm 1.99.0-17 Linux toolchain. Each executable printed 17 after its two-byte input had changed to 29. An empty build printed 29. Each original Cargo fingerprint marked its observing caller complete and fresh. [Original builds and empty-target controls](https://github.com/astral-sh/ohm-cargo/tree/55fc99a09e3bb529294de08dd73f372abae22dd3/benchmarks/ruff-dev-loop-20261027/noquery-established-observer-results)

For each target we made three independent copies and bound each copy to the same absolute source and output paths. The caller and its original complete fingerprint were verified before running Cargo. We changed only the executable at the installed SDK's Cargo path and ran two ordinary builds.

| Cargo executable | First unchanged build | Second unchanged build | Caller compiles across six targets |
| --- | --- | --- | ---: |
| Published -17 | 17, fresh | 17, fresh | 0 |
| Matched release-source control | 17, fresh | 17, fresh | 0 |
| Fixed Cargo | 29, rebuilt | 29, rebuilt | 12 |

The six starting states cover `include_str!`, binary `include_bytes!`, and a tracked procedural-macro file, each with a new timestamp or a timestamp restored to its original nanosecond. The other three units in each fixture stayed fresh throughout. We re-executed and rehashed the final copied executable and the retained original after the experiment. Every original still printed 17, while all fixed copies printed 29. No tests were timed. [Cargo fix](https://github.com/astral-sh/ohm-cargo/pull/261) · [Separate foreign-span source-text upgrade](https://github.com/astral-sh/ohm-cargo/tree/e102d29c7939c6106ac855403c0ad4a11d6e0ea1/benchmarks/ruff-dev-loop-20261027/released-17-foreign-source-cargo-repair)

Run `python3 -B verify.py` to examine the 36 Cargo JSON logs, actual compiler launches, dep-info, saved Cargo fingerprints, hashes and native executions. The modified Cargo was built with release PGO from the source changes in the linked pull request. The installed rustc and its dynamic driver were unchanged.
