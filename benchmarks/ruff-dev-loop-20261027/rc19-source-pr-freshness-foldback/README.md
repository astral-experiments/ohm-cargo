# Failed-producer recovery on the original worktree-seeding branches

Both original Cargo branch heads report E0460 on the first build after reverting a producer whose dependent has already committed. Both corrected branches rebuild the dependency, the dependent library and the binary on that first build. The resulting executable prints 1. All six Linux builds use the physical rustc from Ohm 1.99.0-18, SHA-256 `c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60`. [Cargo #101](https://github.com/astral-sh/ohm-cargo/pull/101) · [Cargo #103](https://github.com/astral-sh/ohm-cargo/pull/103) · [Failed-producer recovery in #280](https://github.com/astral-sh/ohm-cargo/pull/280)

| Branch | Product code | Commit reported by Cargo | Cargo ELF SHA-256 prefix | First reverted build |
| --- | --- | --- | --- | --- |
| #101 original | 62afc4ab | 62afc4ab | 1fca071fbd2b | E0460. First untouched retry succeeds. |
| #101 earlier corrected build | f12e6b41 | 62afc4ab | 0baaacbd2d62 | Succeeds, program prints 1. |
| #101 corrected, fresh profile | f12e6b41 | f12e6b41 | 79fd954d8d32 | Succeeds, program prints 1. |
| #103 original | 1a84f8f3 | 1a84f8f3 | 5be54b31d64d | E0460. First untouched retry succeeds. |
| #103 earlier corrected build | 1cbb910d | 1a84f8f3 | d50a22816772 | Succeeds, program prints 1. |
| #103 corrected, fresh profile | 1cbb910d | 1cbb910d | f5fec208cee2 | Succeeds, program prints 1. |

Each correction touches `src/compiler/fingerprint/mod.rs`. The #103 commit merges its original branch head and the corrected #101 commit. The full source trees, parent lists, Git blob IDs, file SHA-256 values, complete patches, build records, Cargo versions and executable digests are in `results.json`. The two prior corrected binaries kept their parents' version strings when Cargo reused its stamp-producing build script. The final binaries were built in a new dev-derived profile, with the builder's automatic Ohm settings disabled and the subject Cargo's Ohm-defaults feature enabled. Each branch had a distinct target directory and both used the same dependency build directory. The build script's emitted commit, actual lib/bin rustc executions, private SDK's `cargo +ohm -Vv`, and direct native version output agree for both final images.

The checked-in fixture supplies a synchronizing compiler wrapper. It forwards real compilations, models the public-interface hash signal and fails the producer after metadata publication and the application's 16-byte library fingerprint commit. The runner requires a zero-length producer fingerprint before restoring the source. On both parent branches the first reverted invocation compiles the producer and application binary but skips the application library. Rustc emits E0460. All four corrected runs compile all three in dependency order and the linked program verifies the output. These observations establish recovery for this controlled ordering.

## Special files and coverage

The changed preparation path consults the committed short fingerprint for an otherwise filesystem-fresh unit that produces Rust metadata. On Unix it opens with `O_NONBLOCK|O_NOCTTY`, checks the opened descriptor is a regular file, verifies the 16 expected bytes and requires EOF. A successful comparison under exclusive access is consumed once alongside the memoized hash. Shared units can incur an additional short-file open. This qualification measures behavior only.

The original and fixed products each ran with default settings and with `-Zohm-defaults=no`. With a writerless dependency fingerprint FIFO and a directory replacing the application fingerprint, all 12 two-path checks report the application error and exit 101 before the deadline. The original branches make no speculative FIFO open. The corrected products make one nonblocking open. In four additional single-FIFO checks, the final products' later ordinary comparison waits for a writer. The harness terminates the process group after four seconds. The projected syscall flags, deadlines, exits and raw kernel trace digests identify these different outcomes.

Each corrected build series passed 163 tests in total. #101 passed 73 fingerprint tests, seven conditional-metadata integration tests and one seed-marker test. #103 passed the same 81 plus the local-proc-macro-marker test. Each seven-test integration selection physically launched the chosen native Cargo 23 times. Each marker test launched it twice. The fingerprint tests ran in the fixed-source library test binary. `suite-stdout.json.gz` contains the exact passing stdout of all 14 selections across the two series.

Three harness issues remain in the record. The first earlier #101 suite could not write its test temporary directory. The first fresh-profile suite build produced a distinct native Cargo through the tests' additional dependency set and stopped before running tests. The next launcher also stopped before tests because a user-only namespace mapped the host's root owner to the overflow UID. The final private mount namespace preserved UID 1000 and root ownership, dropped all capabilities and bound the separately authenticated product inode read-only at the harness's canonical Cargo path. Each selection checked this identity and its complete version before running.

## Verification

```sh
sha256sum -c --quiet SHA256SUMS
python3 -IB verify.py
python3 -IB test-verifier.py
```

To reproduce the synchronized fixture, use a private rustup home with the intended Cargo and release rustc under its `ohm` alias. Each run requires a new output directory.

```sh
python3 -IB regression/reproduce.py /new/private/result --rustup-home /private/rustup --mode default
```

With the retained build trees, operating-system traces and original fixture packet, the following command reopens the evidence and compares the reconstruction byte-for-byte. The portable packet contains exact regression inputs and passing test stdout, with digest commitments for the larger build, execve and filesystem traces.

```sh
python3 -IB reconstruct.py /path/to/raw /path/to/source-worktrees /path/to/rc19-failed-producer-revert . --compare
```
