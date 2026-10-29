# Cargo can accept an ambiguous method call on an unchanged client

The official Linux Ohm 1.99.0-18 returned success for an invalid `cargo check --workspace`. Adding a second trait implementation to `provider::Token` makes the existing call to `Token.priority()` ambiguous. The caller is a separate workspace crate and its source never changes. An independent empty check of the edited source reports `E0034` in the caller at `client/src/main.rs:3:30`. After a false success, the next ordinary check also succeeded with all four artifacts fresh and no Rust compiler invocation.

| Cargo and Rust | Provider finalizes after the reexporting crate | Provider finalizes first |
| --- | --- | --- |
| Official -18, Cargo 7caf39914 and Rust a4fa11bcd | Twice accepts the edited crate and its next check | Twice reports E0034 on both checks |
| Parent 235f92286 and official -18 Rust | Twice accepts the edited crate and its next check | Twice reports E0034 on both checks |
| Candidate b3360c5ed and official -18 Rust | Twice reports E0034 on both checks | Twice reports E0034 on both checks |

The fixture contains four crates and no third-party dependencies. `api` declares two traits with the same method. The original `provider` implements only the first trait. The edit adds the second implementation and changes an unused private function in the reexporting `reader` from 11 to 12, forcing its compiler to run. Rust reports a changed public hash for the provider and the exact prior public hash for the reader. The error refers only to `client` and names both traits.

The forward-only Linux interposer pauses Cargo's actual metadata-file timestamp call. Rust has already written the metadata and emitted its genuine metadata notification. The held Cargo worker waits until its peer's 16-hex fingerprint exists with a new timestamp and then forwards the original file descriptor and original timestamps. The trace and the recorded file values establish the actual completion order. No source file is backdated and no fingerprints or compiler outputs are synthesized. [Original scheduling experiment](https://github.com/astral-sh/ohm-cargo/tree/0f4c483b2dd7375495c8018a5b5ff2089b73470c/benchmarks/ruff-dev-loop-20261027/rc19-rmeta-publication-order-parent-results) · [Candidate scheduling experiment](https://github.com/astral-sh/ohm-cargo/tree/4d9bfb6089d84628cd6b24badcfbba4ea6720b77/benchmarks/ruff-dev-loop-20261027/rc19-rmeta-publication-order-candidate-results)

In both provider-late rounds on each affected Cargo, Cargo committed the reader as `BuiltUnchanged` while the provider was held. On the matched parent, both client decisions came **after** Cargo had marked the provider changed and written its fingerprint. On -18 one client decision came after Cargo marked the provider changed and the other came before that point. The incorrect recorded reader state suffices in either case. The candidate records `BuiltChanged` when it cannot establish that the reader's metadata dependency is unchanged, so it executes the client's real compiler. All 12 independently empty checks report the same terminal E0034. All restorations succeed and all following checks are completely fresh.

The matched Cargo binaries came from the release-profile pair with evidence-manifest SHA-256 `66f974005cef1bc9841158e1fcac08e249256df89be3aa1d62c920c2e45705b2`. The candidate has only the production fingerprint change in b3360c5ed. Both binaries intentionally report the parent's version stamp. The published -18 archive SHA-256 is `629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8`. Each case records the SHA-256s of the original raw stdout, stderr, syscall trace, observed control file when present, and machine-local result. The per-arm JSON records physical compiler launches, raw syscall line ranges/digests, file identities and the order in which Cargo and Rust published their results. The projector joins interrupted and resumed system calls by thread before counting successful compiler executions. The `compiler-artifact.fresh` field on the falsely successful edited command alone does not identify an actual compiler.

Run the following commands on Linux with the SDK already installed, `cc` and the rustup shims on PATH. The reproduction creates a private rustup alias, source, Cargo home, target, and separate build directory. Use a new nonexisting directory for each run.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
python3 -IB selftest.py
python3 -IB reproduce.py /path/to/installed-ohm-18 /tmp/unique-provider-late provider-late --expect stale
python3 -IB reproduce.py /path/to/installed-ohm-18 /tmp/unique-provider-first provider-first --expect correct
```

Both standalone invocations were separately run against official -18 with the original scheduling interposer, without tracing and without Cargo debug logging. `standalone.json` records their 14 verdicts. Use `--expect correct` for the corrected candidate in either order. To regenerate an arm from its retained private originals, run `python3 -IB project.py /path/to/arm /tmp/arm.json` and compare the result to its matching JSON. Each native cohort uses the same starting target for both controlled orders, running the four order trials from independent copies. All observations here concern correctness and carry no performance estimate.
