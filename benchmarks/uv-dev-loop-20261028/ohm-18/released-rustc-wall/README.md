# Four Cargo and Wild combinations with released Ohm rustc

Each of two uv checkouts ran 24 paired edit blocks for each command. Every block ran the distributed Ohm -18 toolchain, a source-matched Cargo and Wild build, the historical eight changes, and the historical stack with a Wild jobserver retry. All four used the released rustc and target standard library. The standard-library change was compiled into Cargo on the historical arms. The first checkout edited a Homebrew predicate. The other edited its help text.

| Command | Control | First checkout, paired median wall saving | Independent checkout, paired median wall saving |
|---|---|---:|---:|
| `cargo check` | Distributed -18 | +4.00% [-5.31, +10.41] | -5.76% [-35.26, +11.59] |
| `cargo check` | Matched Cargo and Wild | -7.11% [-22.68, +7.47] | +1.01% [-26.79, +6.37] |
| `cargo build` | Distributed -18 | +3.84% [-12.13, +11.61] | +2.69% [-10.42, +10.08] |
| `cargo build` | Matched Cargo and Wild | -0.50% [-9.62, +7.22] | +4.55% [-14.63, +13.19] |
| `cargo test --no-run` | Distributed -18 | +4.43% [-17.32, +14.12] | +2.99% [-5.58, +16.23] |
| `cargo test --no-run` | Matched Cargo and Wild | -3.36% [-34.19, +18.76] | +3.77% [-2.61, +14.45] |

Intervals cover at least 97.73% for each paired median. The historical stack missed its predeclared test against both controls on both edits for every command. The jobserver retry also missed its predeclared test-preparation comparisons. The workload compiled 72 test executables on each test-preparation run. No uv tests ran.

A file-name lookup on separate cores overlapped the last two commands in replica test block 24. The primary result retains all samples. Removing that block gives a median test-preparation saving of 2.99% against distributed -18 and 5.37% against matched Cargo and Wild.

[576 wall times](samples.csv) · [All paired comparisons and exact tests](numeric-results.json) · [Artifact and process checks](audit.json) · [Original logs, frozen assignments and scorer](observations.zip)

To reproduce the numerical results from a fresh directory, unpack the observations and run the packaged standard-library Python scorer.

```sh
unzip observations.zip
python3 -I -B protocol/analyze.py protocol/registered-four-v3.json r18-final
```
