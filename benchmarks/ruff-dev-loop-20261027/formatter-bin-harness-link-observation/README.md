# An empty Ruff bin harness can still require its real native link

On released Linux Ohm 1.99.0-17, a reversal in `ruff_formatter` changed two formatter error messages from “Ruff” to “Rome”. We used the entire `crates/ruff_formatter/src/diagnostics.rs` change from Ruff commit `2b1d3c60faafcedc79423661884331eb8834fab7` on `93526150df078af7dd8fc4226cdcc469539d2001`. The original commit touched 32 files.

Each direction of `cargo +ohm test --no-run -p ruff_python_formatter --locked --offline -j4` emitted 218 units. One full rustc and four link-only rustcs ran. All four invoked packaged Wild behind GCC and collect2. The binary test harness `ruff_python_formatter-81814697f8234e3f` has no tests. Its raw ELF digest stayed `ce80372dd5924bba1bf4639ac1b8d8e92f809540d614ca98fb54fa20f56d783d`. The other three executables changed. An independently compiled ordinary Rust caller printed the changed diagnostics.

## What reached Wild

The bin harness’s genuine 195-argument Wild command explicitly included the changed `ruff_formatter` archive among 135 rlibs. The cached `.rlink` has four Rust objects. The v5 Cargo manifest has no unused-extern result for the harness. The original rustc invocation did not request that report. The ordinary user-written main uses `ruff_python_formatter::cli`, while the test compiler supplies its own executable entry point.

A separately copied target was first 218/218 fresh and matched every original workspace product byte. Both source directions then reproduced the same job counts and harness ELF. We enabled the stock linker’s layout output and joined its selected member offsets and section ranges to the physical rlibs from each run.

| Real terminal | Formatter codegen objects selected on edit and restoration | Formatter input sections retained on each |
| --- | ---: | ---: |
| Binary’s empty test harness | 0 | 0 |
| Library test harness | 50 | 826 |
| Fixture integration test | 50 | 826 |
| Ordinary formatter binary | 50 | 1,043 |

All 50 object member filenames changed. Forty-nine object payloads were byte-identical, one changed, and embedded `lib.rmeta` changed. All 544 ordered archive symbol names and member **ordinals** agreed. The independent replay regenerated its own physical archive. The original and replay digests are reported separately. Adding a single test in the bin’s own source that prints `FormatError::PoorLayout` made the harness select all 50 objects and retain 24 sections. On the same historical edit its five objects and `.rlink` remained byte-identical, while the final ELF changed and the running test printed “Rome”. Restoration produced “Ruff” and the prior ELF. Runtime probes ran outside the build commands.

## An unchanged prior link plan can return the wrong program

The original unmodified bin source and historical edit were replayed with no user linker flags or compiler wrappers. An otherwise absent `libgcc_s.so` linker script appeared in the existing higher-priority `psm` build-output directory of the normal GCC-expanded native search path. It loaded the usual system library and an assembly object defining `write`. The package’s sources, target, native flags and saved objects were otherwise the same as the historic case. On the edit, Cargo chose link-only and Wild still selected zero members from the changed `ruff_formatter` archive. Wild and its worker threads opened the new script and object. The resulting `--list` invocation exited 83. With the shadow removed on restoration, it exited 0, printed its zero-test listing and recovered its exact original ELF. A separate repetition with Wild layout diagnostics disabled produced the same three runtime statuses and matching corresponding ELFs. The ordinary command could therefore return a stale working executable if it skipped the relink based on prior archive selection. The search shadow is a deliberate adversarial filesystem change.

A distinct source-level negative adds an exported `write` implementation to the library without changing the bin source. The real harness then selected 50 library objects and exited 83. This edit triggered seven **full** rustcs, including the harness, so it tests a different path from the shadow experiment.

An independent static native fixture linked the actual Ruff archives behind an immutable script that used the original member filename. With an explicit symbol request, or with `--whole-archive`, the native return values were 42, 41, 41 and 42 across original, edit, restored-source and the exact original archive again. Restoring the source had generated a new physical member name. The matching 243-byte input section occupied a 256-byte output interval. Without either extraction request, all four programs returned 41.

The available Cargo receipt cannot certify earlier missing library-search entries, current script contents or other ambient linker inputs. The physical archive also fails exact-byte admission on the real workload. A link-time implementation would need its own authenticated record of positive and negative resolution, a check for filename-sensitive scripts and auxiliary outputs, and the actual ordered linker inputs. No performance samples were taken. The earlier 399ada4c prototype required a cfg-disabled integration target and a same-package mixed cdylib/rlib dependency. This target is a Cargo binary with a test harness. The separate speculative-test completion work applies to an integration test waiting for its own library and performs a different operation. [Cargo draft #260](https://github.com/astral-sh/ohm-cargo/pull/260)

Run `python3 -B verify.py` to verify the portable receipt. The raw process lines and artifact digests remain in the ledger. Original compiler argument arrays and private per-run files remain on the research host. The exported text substitutes a neutral name for private registry hosts. The scripts expect the frozen Linux SDK, Ruff checkout and isolated prior native states identified in the included worker.
