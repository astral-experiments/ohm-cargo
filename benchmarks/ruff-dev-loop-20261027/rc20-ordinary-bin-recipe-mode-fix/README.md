# Cargo relink collection mode changes on an existing Linux target

Fixed Cargo rebuilt the unchanged binary crate on both mode switches. Switching from the default to `-Zrelink-only=no` changed the executable’s printed value from 17 to 29. Switching back in a separate target changed 29 to 17. Each switched ELF matched an independently empty build byte-for-byte. The preceding released Cargo and #284 had reused the old value in both directions. The separate historical packet has manifest SHA-256 `2ea3d01d54760ac50e00902f83cf638678e0ee320e65d37334aaa80507ec9db7`. [Cargo change](https://github.com/astral-sh/ohm-cargo/commit/e2fa457aa7e8e99275a69bbf2e72856f4b767d0d)

The same fix recovered two already-poisoned build directories on the first invocation. Only Cargo at the installed SDK path was swapped. The Rust sources, target, build directory, compiler, linker and invocation flags for the failing build stayed fixed across the swap. Each fixed build actually ran the consumer’s compiler and returned Cargo exit 101. Its error and primary source location agreed with an independently empty build. The next invocation returned the same error, then switching to the default restored the original successful program and the next invocation was fresh.

| Native fixture | Commands | Observation |
| --- | ---: | --- |
| Executable value, two directions | 14 | Each switch launched one consumer compiler and one stock Wild. The next unchanged build used neither. Both dependencies remained fresh. A genuine source edit and its restoration also ran the compiler and linker in each lane. |
| Diagnostic, new targets | 15 | Default → no and explicit yes → no each rejected the unchanged consumer twice. Freshly compiling the same source under no produced the identical error. Restoring default or explicit yes produced 17. |
| Existing poisoned targets, one SDK path | 18 | Released -19 falsely succeeded twice. In the other target original #282 falsely succeeded twice and then original #284 still succeeded with zero consumer compilers. Fixed Cargo rejected both histories immediately. One independently empty failing check completed the migration control. |

All 47 visits used ordinary `cargo +ohm build` with the selected mode and private stores. The fixtures use a re-exported proc macro that observes the actual compiler arguments. In the value fixture the whole default ELF was `8eb26f70a8cf94128edbe71fde7f67616f889fa8235d080258a72ee90db3196d` and the whole no-mode ELF was `d93fbb1a03a173f5254aabd94405e1635d64c586212ae83a548e643fb8603dfc`. Running each successful diagnostic ELF printed 17 and its hash was `523d6d03d22f65556de5dcdea9c6aad2cbe4ea228485515961d4b229325c1815`. All eleven rejected unchanged or cold invocations reported `link recipe was not requested` at `consumer/src/main.rs:1:28`. The actual root arguments had both the facade rlib and the facade rmeta. Failed consumer compilation generated no successful consumer-artifact JSON message. The kernel traces supply the compiler counts in those cases.

## Images and native evidence

The fixed Cargo was built with the distribution PGO profile `481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7`. Its source was `e2fa457aa7e8e99275a69bbf2e72856f4b767d0d`, tree `da9c1246f3ad023da25fb60979a5e486863233e2`, binary `6d0449d4eb0aa490e04aa553bab278c7818efe2c7d529b1d5c9536f01ef90168` (43,342,056 bytes). The physical H8 frontend and stock Wild came from the official Linux -19 distribution, SHA-256 `ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812`. The driver and executable hashes, four Cargo versions, six consecutive swaps, private transport SHA-256s, and original raw result and build commitments are in [subjects.json](subjects.json).

The unwrapped Linux jobs ran on two pinned CPUs with syscall tracing of successful and attempted process execution. The projection authenticates all 1,513 individual syscall files, and records all 261 successful exec calls. These include 44 crate compilers, 48 compiler queries, 47 rustup proxy calls, 47 selected Cargo calls, and 25 each of the C driver, collect2, and stock Wild. Wild is identified at the actual `wild-ld/ld.bfd` executable. The diagnostic worker’s original generic linker counter omitted that spelling. This packet obtains all native counts from the raw successful execs. Empty diagnostic builds also linked the proc-macro DSO before the unchanged consumer failed.

The earlier historical matrix copied a template containing a previously edited main.rs and wrote the registered main.rs text before its first run. The source digest recorded per row is the one actually compiled. The copied origin and facade sources match the fixture. The two subject programs and all observed native jobs are small Linux correctness cases. These commands did not collect performance evidence.

## Offline verification and replay

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
```

The offline verifier checks the total and per-phase job counts, Cargo artifact rosters, raw stream and argv commitments, exact clean diagnostics, switch image identities, stable Cargo process paths and exact executable identities. Six synthetic mutations cover a stale program, false freshness, changed ELF, missing diagnostic, misattributed historical Cargo, and omitted native evidence.

To rerun with `rustup` proxies and `strace` on Linux, supply a new directory on a volume owned by the caller, the exact official -19 SDK, and the three named original/fixed Cargo files. Distinct targets and a linked private `+ohm` toolchain are created below that directory.

```sh
python3 -IB replay.py NEW_DIRECTORY OFFICIAL_19_SDK ORIGINAL_282_CARGO ORIGINAL_284_CARGO FIXED_CARGO
```

For the value test alone, pass a complete SDK with the fixed Cargo already installed.

```sh
python3 -IB replay-values.py FIXED_SDK NEW_DIRECTORY --expect correct
```

The signed SDK and every Cargo executable were checked against their exact SHA-256 before native acquisition. The H8 diagnostic changed only the free-disk guard from 45 GiB plus 600 MiB to 24 GiB plus 600 MiB. The same-path driver used a new worker-relative private root and the H8 guard on its two durable-space preflights. Its original 105, 100 and 68 MiB local allocation checks remained. No host-specific paths, response contents or environment strings are included in the projection.
