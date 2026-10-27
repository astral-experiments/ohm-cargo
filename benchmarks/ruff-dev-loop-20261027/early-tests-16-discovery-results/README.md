# Cold Ruff test compilation with the shipped Ohm 1.99.0-16

Two first-use Linux builds compiled the complete locked Ruff workspace at 93526150df078af7dd8fc4226cdcc469539d2001. The default command was `cargo +ohm test --no-run --locked --offline -j8 --message-format=json`. The other command added `-Zohm-early-tests=no` before `test`. Each received an empty target and shared build directory, the same canonical paths, independently seeded verified registry packages, and the official compiler, Cargo and Wild. Both used the stock trust defaults. The commands compiled the test targets without executing them.

| Observed on one fresh run per configuration | Stock | Early tests disabled |
| --- | ---: | ---: |
| Cargo artifact messages, all dirty | 619 | 619 |
| Executables reported by Cargo | 102 | 102 |
| Full rustc invocations | 636 | 623 |
| Distinct complete rustc argument vectors | 623 | 623 |
| Wild invocations | 200 | 188 |
| Distinct Wild destinations | 188 | 188 |
| Rust compiler configuration queries | 36 | 36 |

All 110 final ELF files had the same entire file SHA-256 across the two states. Cargo reported 84 executables with the test profile bit and 18 other binaries or examples. The ELF inventory additionally includes shared libraries. The table counts native processes; the nested GCC/collect2 numbers in the raw results can also include native build scripts.

The stock scheduler logged 21 successful provisional executions and 13 retries. Twelve first invocations exited successfully and actually passed their own producer rlib to Wild. Their retries did so again. In all twelve cases the producer rustc had already exited successfully and Cargo had published its library artifact before the earliest scheduler start compatible with the test job clock. One genuinely overlapping `ruff/tests/integration_test.rs` invocation exited with ordinary Rust status 1, before reaching Wild. The second compilation and its link succeeded. All 13 terminal binaries were byte-identical to those from the disabled control. These observations qualify redundant work on this machine and command without estimating elapsed performance.

Three of the twelve late starts have an additional independent observation. A sibling using the same producer had already logged an acceptance or retry from after `Completion::wait()`. For the other nine the completion-state inference uses the shipped control flow. The last logged producer job-queue `end` was observed *before* the native producer rustc exited and therefore could not be its final completion. The artifact arrived later, more than 1.5 seconds before the conservative lower bound for starting this test job. The scheduler releases held output and settles the stored final result in the same call before launching the next job. Stock Cargo does not log the contents of its `Completion` state. The observations distinguish native exits, artifact publication and inferred confirmation; a test of the new Boolean check needs the changed Cargo. Source spellings are incidental.

`thirteen-targets.json` gives each producer and test PID, exit/SIGCHLD, matching argument hashes, native self-rlib paths, timestamp bounds and Cargo policy record. The typed-process archives cover all rustc and Wild calls. The Cargo-output archives retain complete stdout, stderr, clock-chunk maps, individual executable/ELF identities, registry checksums and input guards. Where needed the portable text replaces one private registry directory name. `originals.json` binds the original and portable file digests, and counts substitutions. Byte offsets in clock records address the original unmodified byte stream. The full private strace is preserved separately. Run `python3 -B verify.py` in this directory to verify the packet and recalculate the table.
