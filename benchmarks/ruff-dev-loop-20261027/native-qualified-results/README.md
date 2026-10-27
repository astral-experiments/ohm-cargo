# Ruff build and test-build timings for Ohm Rust #233

Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. The candidate is the release PGO/BOLT compiler built from `27029b4bce40f3b5497add5019c02a11c16c4c18`. All compiler arms used the same Cargo binary. Each edit and command got twelve balanced pairs of ordinary untraced invocations, six in each order. The timer covers the complete command, including its rustup proxy, and test-build stops before executing any tests.

| Edit | Command | Control | Median seconds | Paired time reduction, 95% CI | Faster pairs | Holm p |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Private linter doc correction | build | Previous #233 | 12.81 → 11.06 | 14.3% [8.6, 20.1] | 11/12 | .0087 |
| Private linter doc correction | test --no-run | Previous #233 | 12.73 → 11.64 | 11.4% [1.5, 19.8] | 10/12 | .0303 |
| Parser diagnostic | build | #232 | 21.63 → 6.01 | 72.1% [69.7, 74.3] | 12/12 | .0087 |
| Parser diagnostic | test --no-run | #232 | 33.23 → 11.69 | 65.4% [61.3, 69.3] | 12/12 | .0087 |

The four p-values use an exact two-sided test over the 924 balanced assignments. Confidence intervals use a 20,000-draw paired bootstrap on log elapsed-time ratios. The unchanged commands immediately after the doc edit were registered as a separate two-comparison family. The build repeat went from 0.862 to 0.661 seconds (21.3% paired reduction, 95% CI 7.7% to 32.7%, adjusted p=.0346). The test-build repeat went from 0.657 to 0.744 seconds (−21.4% paired reduction, 95% CI −60.4% to 3.5%, adjusted p=.2208). Both registered comparison families are shown. [Original registration](https://github.com/astral-sh/ohm-cargo/blob/804c80a25fd2bbf29d7c48bc8327eda8bbfef493/benchmarks/ruff-dev-loop-20261027/native-observed-sources/plan.json)

Run `python3 -B reproduce-timings.py` in this directory to recalculate both families from the paired command receipts. The CSVs give the 96 individual edit timings. The receipt archive also contains the ordinary unchanged timings, unit freshness and independently collected process counts. The original source, index and benchmark process identification were checked at the end of each paired series.

## Compiler and linker invocations

| Edit | Command | Full rustcs, control → candidate | Candidate link-only rustcs | Wild, both arms |
| --- | --- | ---: | ---: | ---: |
| Private linter doc correction | build | 11 → 2 | 2 | 3 |
| Private linter doc correction | test --no-run | 26 → 4 | 16 | 19 |
| Parser diagnostic | build | 35 → 3 | 6 | 8 |
| Parser diagnostic | test --no-run | 93 → 6 | 62 | 67 |

The first and last independent traces gave identical process counts and crate names. The next unchanged command required zero rustcs and zero Wild invocations across 501 build units or 619 test-build units. The doc edit matched #232's reference count of two and four full compiles.

Both repeated edited outputs were compared with an independent clean candidate build. Both corrections produced 15/15 byte-identical build ELFs. The doc test-build produced 109/110 and 107/110 byte-identical ELFs in the two comparisons, and the parser test-build produced 110/110 and 109/110. The only differences in recorded ELF section contents and header fields were the build-ID note digest and `.rodata`'s `sh_entsize`. The full diagnostic JSON and the artifact roster matched the clean build.

Comparing the parser's edited program to the original source instead, eight build outputs and 58 test-build outputs changed beyond those two recorded linker fields in both traces. For the doc edit, all 15 build ELFs were byte-identical, and zero and two of the 110 test-build ELFs differed in the first and last traces, solely in those two recorded fields.

The original private pattern-recovery `cargo check` edit compiled only `ruff_python_parser` on both #232 and #233, with all 520 units fresh on the subsequent check. A genuine change to the `dataclasses.field` matcher changed the RUF008 diagnostics from two to one and back to two on restoration, under both `build` and `test --no-run`.

## Reproduction

Run `python3 -B verify.py` to check the published file hashes, recompute all paired estimates, rebuild physical process counts from typed exec records, compare the ELF sections and replay the check and linter controls. Each endpoint archive contains only command receipts, binary/section digests and typed rustc/Wild witnesses. Traced invocations were collected separately from ordinary timing samples. [Compiler head](https://github.com/astral-sh/ohm-rust/pull/233) · [Compiler correctness controls](https://github.com/astral-sh/ohm-cargo/tree/a77f8632fa52bfac7445d5448a19b2fe4817350d/benchmarks/ruff-dev-loop-20261027/native-observed-sources/release-qualified)

To exercise a single historical edit on Linux, use a clean linked Ruff worktree at the pinned commit and an offline Cargo registry containing its locked dependencies. The helper records the active tool hashes, checks the diagnostic against the edited executable and restores the source and index. The candidate binary hashes below are for the exact measured toolchain.

```sh
python3 -B rerun-native-edit.py /path/to/ruff-worktree parser build \
  --target /path/to/ruff-target --shared-build /path/to/ohm-build \
  --expect-driver dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f \
  --expect-cargo a99a694c680f474bef2ae17de20533890dc536606021db93aaf531e3ef40919a
```

Select `doc` or `parser` and `build` or `test`. With `--trace-edit /new/private/directory`, the helper records the edited command's execs and omits its wall time. Use a separate worktree target for each compiler comparison.
