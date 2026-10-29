# Fingerprint the effective relink-cache collection setting

Changing to `cargo -Zrelink-only=no build` could accept a binary crate that an empty build rejected. The compile-time witness is a reexported proc macro that inspects rustc’s actual `emit-rlink` argument. The macro expands to `17u8` when the argument is present and to a compile error when it is absent. The fixture uses ordinary path dependencies and the published Linux compiler. Cargo passes different arguments in the two modes even when both modes run full codegen.

Released Ohm `-19` and the previous combined Cargo #284 both returned success twice after the switch, with zero root compiler processes. Removing just the root’s 16-byte committed fingerprint made the next command invoke rustc and report the error at `consumer/src/main.rs:1:28`. The independent empty build reported the same error. The 33 commands here independently separate those two source lines and compare explicit `yes` with the default. These additional observations used the same signed `-19` rustc and its stock linker. [Ordinary Ruff build and compiler-argument checks](https://github.com/astral-sh/ohm-cargo/tree/c79b361fae6b0cbb51468f23cdb6749023e899a4/benchmarks/ruff-dev-loop-20261027/rc20-ordinary-bin-recipe-boundary)

The fix adds the effective collection setting to the native target fingerprint already tracking cached codegen in #282. The new testsuite case passed when bound to the fixed release-profile Cargo. Bound to the original #282 binary, the same test executable failed because the expected full compiler invocation was absent. The existing assembler regression test passed on the fixed binary. The test binary contained 4,821 cases. These results cover the two named cases. An initial harness mount prevented rustup from opening `/dev/null` and launched zero Cargo processes. Both final tests used a device-enabled mount and verified the bound program by hash. [Cargo #282](https://github.com/astral-sh/ohm-cargo/pull/282)

An independent host observed the corrected `17` and `29` executables, exact empty-build diagnostics and first-command recovery from two poisoned targets. It also replaced #282 with the old #284 under the same SDK path. That operation alone preserved the false success. Across the 47 commands, the recorder captured 44 crate compiler invocations, 25 stock Wild links and 261 successful program launches. The separate packet includes a runnable four-image reproduction. [47-command replay and source](https://github.com/astral-sh/ohm-cargo/tree/c7b5b17cdf17f98f63592d3c3d9c7d5986801a42/benchmarks/ruff-dev-loop-20261027/rc20-ordinary-bin-recipe-mode-fix)

The source audit inspected the current code at 297 distinct Ohm Cargo branch and PR heads, including 74 different fingerprint source blobs. Only #282 and its two descendants contained the old boolean marker. All three omitted the collection setting. The local merge commits preserve the original added and removed lines of each cache-writer PR and carry the new fingerprint and regression test into both descendants.

Two earlier local fixture setups stopped before completing their controls. The first could not start Cargo under the sandbox’s process tracer. The second recorded four successful Cargo calls per image, then looked in the wrong directory for the split-layout fingerprint. The completed 33-command data uses the actual private target-owned fingerprint. No timing measurements enter this report.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
```
