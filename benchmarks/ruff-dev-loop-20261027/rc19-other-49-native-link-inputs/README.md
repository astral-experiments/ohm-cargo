# Ruff workspace native link inputs on Linux Ohm 1.99.0-18

| Evidence | All 50 test executables | Other 49, excluding `ty_server:e2e` |
| --- | ---: | ---: |
| Registered a Cargo dependency on the one `ron` unit in each of three scheduler runs | 50 | 49 |
| Passed literal `-lutil` through GCC, collect2 and stock Wild in both full native traces | 50 | 49 |
| Passed the writable Cargo `psm` native search root ahead of the system roots | 50 | 49 |
| Also passed a `zstd-sys` output directory ahead of the system roots | 34 | 33 |
| Passed a direct `libron-*.rlib` to Wild | 35 | 34 |
| Exited 83 when the released toolchain rebuilt and executed the actual Ruff test executable under an earlier `psm/out/libgcc_s.so` | 50 | 49 |

The join uses all 50 exact Rust test output basenames and the owning package. The three queue histories cover 30 integration tests, 17 library harnesses and 3 binary harnesses. Two histories retained all 150 native argv vectors and parent/child identities per history. Every parent and child exited zero. The diagnostic Cargo contains tracing on the shipped Cargo source, with the released Linux rustc and stock Wild. Each `-lutil` was already literal on entry to GCC and appeared under dynamic search at Wild. Both histories agree on the per-target native build directories and direct RON rlib. [Queue source and trace commitments](https://github.com/astral-sh/ohm-cargo/tree/46767bab62f2cb4295410150ecbd77d4a12320fd/benchmarks/ruff-dev-loop-20261027/rc19-native-queue-opportunity-h8)

The official installation independently captured the same set of 50 named outputs in two physical cache namespaces. Its custody census found an absent `libgcc_s.so` under the build user's writable `psm` search directory for each. A single added provider in the active namespace affected every actual Ruff test ELF. All 50 were invoked with `--list`, exited 83 and listed zero tests. A malformed provider made Cargo exit 101 after eight native starts. Removal restored all 50 original ELF hashes. The per-target digest ledger links every original, changed and restored output and the available native exec traces. [Official released target and executable census](https://github.com/astral-sh/ohm-cargo/tree/3ec6efbb651be21e2227b8ee33f701fb011a2fc8/benchmarks/ruff-dev-loop-20261027/rc18-release-ruff-link-census)

The original queue exec traces and the official shadow exec traces record successful process launches. None supplies a per-process `ENOENT` for the candidate `psm/out/libutil.a` in those workspace runs. These cells use JSON null. A separate one-worker replay of the exact released `ty_server:e2e` argv, inputs and baseline ELF retains a recipe tied to the kernel file-observation digest. It records negative `libutil.{a,so}` entries below both eligible build directories and a positive system archive. It counts for that individual replay. In a separate ordinary single-program Cargo fixture, the verified syscall lines themselves record `libutil.a` missing in a sibling build script's `OUT_DIR` and opened after insertion. Its actual program returned 41, 83, 41 and 83 across baseline, addition, removal and a same-length/backdated content change. Independent empty builds reproduced the relevant ELF hashes. That archive substitution did not run once per Ruff target. [Released one-target replay](https://github.com/astral-sh/ohm-cargo/tree/3ec6efbb651be21e2227b8ee33f701fb011a2fc8/benchmarks/ruff-dev-loop-20261027/rc18-release-ruff-link-census/single-archive) · [Single-program archive and actual lookup syscalls](https://github.com/astral-sh/ohm-cargo/tree/6680c887512650c45d2e877a0b73383ea288c8ce/benchmarks/ruff-dev-loop-20261027/rc18-exact-rlib-native-boundary)

To reconstruct the compact ledger, supply the existing evidence Git checkout, the unchanged H8 full native reports directory containing `instrumented1/native.json` and `instrumented3/native.json`, and the retained released e2e capsule `release-e2e.tar.gz`. The script reads the published Git objects and validates both original native-file commitments. The SHA-256 digest is over its standard-output bytes, including the final newline.

```sh
python3 -IB verify.py "$EVIDENCE_GIT" "$NATIVE_REPORTS" "$RELEASE_E2E_CAPSULE" | sha256sum
gzip -dc targets.json.gz | sha256sum
```
