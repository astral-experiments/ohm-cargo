# Four original Cargo generated-cache writers

All four public heads are active non-draft PRs as of the timestamp in `index.json`. Each has an independent local successor with an actual original and repaired executable. These programs reproduced the write through a symlink to an unrelated fixture-owned file, and verified that the repair replaced the final directory entry. Original executable inputs, outputs, typed Cargo rows and checksums are retained for the 76 completed commands. The #147 initial unsupported compiler probe is recorded separately.

| Original PR | Local repair | Native Cargo commands | Packet SHA-256 |
| --- | --- | ---: | --- |
| [#53](https://github.com/astral-sh/ohm-cargo/pull/53) | `d387f81545e8` | 18 | `0c0b6853f20e8be9b2ffa2a9df861fccb4f28c8bbd99d44b9eabaffc3df6d5d2` |
| [#66](https://github.com/astral-sh/ohm-cargo/pull/66) | `8a99bfff54ed` | 18 | `7b50ccd5b7f8a3db21314a13d075619e7b4b335910af12aac71d90a73a378711` |
| [#75](https://github.com/astral-sh/ohm-cargo/pull/75) | `91330591a68b` | 8 | `7ca52dc9dd098c3fda3eb94af5cf648154e2c4aaab234e963eea383ea848a4d5` |
| [#147](https://github.com/astral-sh/ohm-cargo/pull/147) | `431ff29f460d` | 32 | `14c681b596a11be68688d271fb3eac4b62db91f3c595a2086398331bf5ab20da` |

The shared filesystem helper has the same source blob as the separate #51 manifest repair. Each later branch integrates only this helper before its own caller change. The #53 combined successor preserves both local heads as Git parents. It also qualifies their interaction on the early metadata transport. Full commit hashes, parent relationships, executable hashes and packet digests are in `index.json` and `source-graph.json`. The conditional merge result for #51 records a source compatibility check. A separate direct-child audit found that updating #53 to this combined head requires resolving a conflict in `src/compiler/fingerprint/mod.rs` on the current #52 branch. That child is outside this native qualification.

The original #147 compiler option failed at target discovery on Linux 1.98.1-1. The successful check-hint controls use the released -18 compiler with the historical Cargo’s ordinary settings and the 1.98.1-1 compiler with the historical Cargo’s independent `-Zheadstart=no` option. Each compiler also has a separate no-defaults contrast. The four writers and their precise triggering conditions are covered in `review-notes.md`.

Run `python3 -IB verify.py` to check every shipped file and all behavioral receipts. The reproduction sources and four individual patches are in the corresponding packet directories. The independent combined #53 source and tests are in `packet-53-combined`.
