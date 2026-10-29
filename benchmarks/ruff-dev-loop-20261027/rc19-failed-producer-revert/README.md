# Retrying an interrupted producer after source reversion

The published Linux Ohm −18 distribution returns E0460 on the first reverted build in the checked-in Cargo test `conditional_metadata_rebuilds_committed_dependent_after_failed_producer_is_reverted`. The first unchanged retry succeeds and the genuine executable prints 1. No incorrect executable ran. This particular witness uses Cargo's original test wrapper to hold a producer open after metadata emission, let its dependent library commit, then intentionally fail the producer. The wrapper models the public-interface hash signal and forwards real compilations to the release compiler. Further evidence is required to establish this exact failure in a project without that wrapper.

| Independently built or installed Cargo | First reverted build |
| --- | --- |
| Before conditional metadata, f3e7a43f | Cannot reach the prerequisite. The consumer correctly waits and the synchronization test times out. |
| Original conditional-metadata commit 242e7bdc | Compiles producer, intermediary library and binary, then prints 1. |
| Default-seeding parent 88bd5ae1 | Compiles all three, then prints 1. |
| Its direct child af091eb2, enabling checksum-backed worktree preparation by default | Omits the library. The real binary compiler rejects the inconsistent metadata with E0460. |
| Installed −18, qualified 235f9228, both b3360c5e images and private 3ea3d256 | Same E0460. |

All nine test-harness trials used independently empty physical roots with the same compiler SHA-256, c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60. Every trial except the pre-conditional-metadata parent reached the recorded producer failure after the consumer committed. The parent and child straddling the default change are verified using the exact same checked-in test without product source edits. Historical products were built with Cargo's `ohm-defaults` feature using a private −18 SDK. The release archive and individual tool digests are in provenance.json. [Original test](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/tests/testsuite/freshness.rs#L3990). [Default-change commit](https://github.com/astral-sh/ohm-cargo/commit/af091eb21f940445b6447a3f33dc610a8c291f24).

A separate release-only experiment changed one public const from 1 to 2, confirmed the dependent's new short fingerprint was committed and the failed producer's was truncated to zero bytes, then restored the original source in place. On the default path the producer sees its original content checksum and its previous dep-info, but its empty completion fingerprint still makes it run. The library prepared as fresh using the previous producer generation. Rustc saw that library alongside the newly emitted producer and reported E0460. The next unchanged call saw the newer producer timestamp, rebuilt the library and binary, and printed 1. The same source inode, mtime and content remained fixed during the failed reverted build and successful retry. The explicit setting `-Zohm-worktree-seeds=no` let the genuine mtime change propagate to the consumer. Adding only `-Zchecksum-freshness` restored the failure. [Cargo checksum selection](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/compiler/mod.rs#L207).

The retained measurements include physical rustc role order, hashes of the raw process traces/stdout/stderr, artifact contents, phase return codes and program values. Four initial setup attempts failed before exercising the product, and the first historical checkout lacked Git blobs. Their commitments are retained separately. The original-phase filesystem times are observations without wall-performance interpretation.

```sh
python3 -IB verify.py
python3 -IB reproduce.py /new/private/failure --rustup-home /private/rustup --mode default
python3 -IB reproduce.py /new/private/success --rustup-home /private/rustup --mode seeds-off
python3 -IB reproduce.py /new/private/explicit --rustup-home /private/rustup --mode checksums-only
```

The private rustup home must have an `ohm` toolchain alias for the intended Linux SDK. The runner uses an independently empty directory for each invocation, a real rustup Cargo proxy, `strace`, and the original checked-in wrapper and package files. The first two commands after the offline verifier were also executed against the actual archive. `source-crossover.json` covers all four switch configurations.
