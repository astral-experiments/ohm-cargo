# H8 whole-workspace Cargo admission

Zero instruction samples were collected for the #261 parent and depfile port on this 501-unit Ruff workspace. The final native check kept the original two rejected attempts and followed the prospective stock → parent → port order twice. [Original study](https://github.com/astral-sh/ohm-cargo/tree/c776e0cc7a0cbda6955c67ad4f306676871ab822/benchmarks/ruff-dev-loop-20261027/settled-cargo-depfile-over-observer-workspace-plan), [cache-directory amendment](https://github.com/astral-sh/ohm-cargo/tree/aa182ed7da38300abf446745247df297c3021008/benchmarks/ruff-dev-loop-20261027/settled-cargo-depfile-over-observer-workspace-trust-plan), [final union registration](https://github.com/astral-sh/ohm-cargo/tree/d3984f7b4e9b88ac99ee3f37ca53e12e4a4283d5).

Every native Cargo invocation reported all 501 units fresh, produced the same roster of 922 artifacts, kept all 58 public depfiles byte-identical, and executed only the rustup dispatcher and the selected Cargo program. The preregistered worker verified each originally pinned artifact's full hash, device, inode, size and nanosecond mtime before and after every command. It also rehashed the source and Git index and permitted stamp changes only on the two existing wasm library depfiles. The complete initial values, genuine Cargo JSON and each successful before/after gate are included. Repeated artifact byte reads were checked in the worker without storing six duplicate copies of every file.

| Phase | Cargo | Different registry slots opened for reading | Registry installs | Git slots opened |
| --- | --- | ---: | ---: | ---: |
| Prime | Packaged | 368 | 4 | 1 |
| Prime | #261 parent | 396 | 5 | 1 |
| Prime | Port | 397 | 4 | 1 |
| Verify | Packaged | 372 | 0 | 1 |
| Verify | #261 parent | 399 | 2 | 1 |
| Verify | Port | 399 | 2 | 1 |

After priming, each matched Cargo first wrote the authenticated key for `notify-8.2.0` (`6a03d1395a8f1f0d03809821f1eb453e080a81fc48bd833e8079e670a60fe24a`) into a temporary file and successfully renamed it to `.ohm-registry-json-v2/3d1`. It then installed `rand_core-0.10.0` (`d873d193d5ef46de8e21b2e259cb7cd275e4facbbabf0d12bb8ca67ec74a9d25`) at that same path. The before/after content hash of every slot agreed in each command. The inode or timestamp inventory changed at `3d1`. Packaged Cargo left the primed store untouched. The observed change violates the registered immutable-store precondition in both matched arms. The independent 268-unit H7 linter result measures the port on #261. The earlier release-base 501-unit result uses different Cargo binaries.

In the first eligibility attempt a group-writable ancestor disabled both real proof stores. Changing the private root mode to 0700 enabled them. The next attempt stopped because packaged Cargo and the #261 parent left different registry inventories. Their embedded Cargo commit stamps contribute to the registry entry key. All 732 entries after that attempt match real manifests, with 366 entries per stamp. Both original attempts and the final six native builds preceded any H8 scoring grant.

Run `python3 -B verify.py` from this directory. It replays the 501-unit native output checks, joins raw magic/key writes with successful same-PID atomic renames, checks all six chronological proof inventories and verifies all published checksums. The private originals preserve full strace output. The published subset contains successful proof opens, exact magic/key writes and installs, plus digests of every original per-PID trace. The local registry mirror basename in Cargo JSON is normalized and the original digests are retained.
