# The location of the Ohm SDK changes repeated Ruff workspace test builds

On the packaged Linux Ohm 1.99.0-16, placing the SDK in a directory named `Ohm SDK` caused every unchanged Ruff workspace test build to compile `ron` and invoke the real Wild linker 50 times. With the same SDK mounted at `Ohm-SDK`, the first unchanged test build trained the observer, and both subsequent builds were fully fresh. The original checkout and target and build paths were the same across both SDK layouts.

| Workflow on Ruff | Units | First unchanged command | Second and third unchanged commands, each |
| --- | ---: | --- | --- |
| Spaced SDK, workspace test build | 619 | 1 compile and 50 links | 1 compile and 50 links |
| Hyphenated SDK, workspace test build | 619 | 1 compile and 50 links | 0 compiles and 0 links |
| Spaced or hyphenated SDK, workspace build | 501 | 0 compiles and 0 links | 0 compiles and 0 links |

Each of the four empty states had its own private target and shared build directories. The same Cargo, rustc and Wild binaries built the original Ruff sources. The command was `cargo +ohm test --no-run --workspace --locked --offline -j4` or `cargo +ohm build --workspace --locked --offline -j4` with Cargo JSON for attribution. The observer remained incomplete for all three unchanged test builds using the spaced SDK and was complete from the first repeat in the hyphenated control. All 102 reported native executables were retained. Between consecutive spaced-path test builds, 100, 100 and 101 respectively had identical raw bytes. All six native build executables stayed byte-identical after each unchanged build. No test body ran.

The earlier whole-workspace test attempt placed the space in the target directory. Ruff’s jemalloc configure script rejected that prefix. This experiment moves the space to the SDK directory and verifies rustc's effective sysroot in every cell. The package-level target-directory reproduction remains independent. [Original package experiment](https://github.com/astral-sh/ohm-cargo/tree/d269a2b9b0f2792ed3753b1c058b36af9a9ba5b0/benchmarks/ruff-dev-loop-20261027/released16-spaced-ruff-package)

Run `python3 -B verify.py` to reconstruct successful rustc and linker executions from the actual execve records. The verifier joins them to Cargo units and checks native product digest records, the observed input trailer and the actual command status. The export contains 27,576 entries. One host-specific registry basename was replaced in 1,812 entries. Original and portable digests are recorded separately.
