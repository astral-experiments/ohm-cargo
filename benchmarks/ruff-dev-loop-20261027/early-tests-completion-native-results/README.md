# Whole integration-test jobs after library completion

The guarded Cargo compiled and linked a newly selected Ruff integration test once. Both released Ohm and the matched parent compiled and linked it twice. The complete workspace command needed two full rustc processes and two actual Wild invocations with the guard. Both controls needed three of each. All 110 native outputs and the selected test inventory matched byte for byte.

| Workspace test build | Cargo | Full rustc | Distinct compile commands | Actual Wild | Distinct link destinations |
| --- | --- | ---: | ---: | ---: | ---: |
| First selection after the test edit | Packaged -16 | 3 | 2 | 3 | 2 |
| First selection after the test edit | Matched parent | 3 | 2 | 3 | 2 |
| First selection after the test edit | Guarded candidate | 2 | 2 | 2 | 2 |
| Empty workspace build state | Packaged -16 | 636 | 623 | 201 | 188 |
| Empty workspace build state | Matched parent | 636 | 623 | 200 | 188 |
| Empty workspace build state | Guarded candidate | 623 | 623 | 188 | 188 |

The cold candidate produced 110 raw-identical ELF files relative to the official SDK. The independently rebuilt cold parent produced 109 identical files. The remaining parent's output differed only at the allowed GNU build ID or Wild .rodata section field, with the rest of the ELF byte-identical. The complete comparison retains exact values and digests. Each arm reported 619 Cargo artifacts, 84 test-profile executables, and 18 additional binaries or examples.

The first selection follows the full historical test-only change 1b9310471b on a real Ruff checkout at 93526150df. Its test workspace was seeded with `cargo test --no-run --workspace --exclude ty_server`. An unchanged seed was completely fresh, the normal ty_server library was already present, and the ty_server e2e executable was absent. Each separate workspace state received the complete reversal of the historical edit. The underlying source checkout stayed clean. The cold controls used the original source and independently empty build and target directories. All six commands used the shipped Rust compiler and Wild, eight jobs, default trust, and the same canonical paths.

The added Cargo regression failed at two compiler invocations on the stock source and passed at one on the candidate. The existing producer overlap and failure controls passed. The workspace commands compiled the tests without executing them. Listing the selected test harness after each command verified its inventory.

The original ELF reader stopped on an unsupported Python mmap method while examining the second cold control. The corrected reader reused all five existing command outputs and ran the remaining cold candidate once. All timings remained unopened. This packet binds 15,256 native records, including successful execve streams, process terminal records, source/unit inputs, real Cargo output and behavior-test output. One host-specific registry basename is replaced in 1,389 text members. Original and portable digests are in inventory.json.gz. The full compiled binaries remain on the qualification host.

Run `sha256sum -c SHA256SUMS` and `python3 -B verify.py` to rederive the complete compiler/linker rosters from the captured execve calls. This is an unscored structural qualification. [Release source and packaged A/A controls](https://github.com/astral-sh/ohm-cargo/tree/a5f4d61e00f43733b5f5f9b724fd6844ab00a0fd/benchmarks/ruff-dev-loop-20261027/early-tests-matched-release-subjects) · [Revised timing registration and ELF reader](https://github.com/astral-sh/ohm-cargo/tree/1844efed56043bca3add46f9ccac806a17af829c/benchmarks/ruff-dev-loop-20261027/early-tests-completion-wall-plan-v2)
