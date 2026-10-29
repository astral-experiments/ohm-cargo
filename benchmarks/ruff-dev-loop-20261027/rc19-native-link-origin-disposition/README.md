# Historical Cargo integration-test links

Cargo #72 introduced the wrong native result on its active branch. Its direct parent, #71, rebuilt the integration test after its unused package library changed and selected the updated native provider. The #72 head kept the executable, even though the real linker would produce a different program or reject a malformed input. Closed #28 independently exhibits the same defect on the older source line. The two heads are on different branches. Their respective downstream #29 and #73 extend the optimization. The observed failure uses real rust-lld and predates the bundled Wild configuration in #139. [Cargo #28](https://github.com/astral-sh/ohm-cargo/pull/28) · [Cargo #71](https://github.com/astral-sh/ohm-cargo/pull/71) · [Cargo #72](https://github.com/astral-sh/ohm-cargo/pull/72)

| Historical source | Separately staged valid provider | Malformed provider and repeat |
|---|---:|---:|
| #72 direct parent, 242e7bdc | 29 | Cargo 101 twice |
| #28 head, f56167ae, Ohm defaults | 17 | Cargo 0, program 17 twice |
| #72 head, 0d46e411, Ohm defaults | 17 | Cargo 0, program 17 twice |
| Either affected head with Ohm defaults disabled | 29 | Cargo 101 twice |
| Separate codegen port, 15d40ff2 | 29 | Cargo 101 twice |

Both heads and the direct parent were built with the Ohm defaults feature, then paired with the same official -18 rustc. The original building and testing processes ran unprivileged on Linux x86-64. The private GCC control has a pure Rust test, no native declarations, no build scripts and no extra compiler or linker flags. A private copy of the installed GCC runtime script injected an object that exits 83. The old head continued to exit 0 and accepted malformed script bytes. The port, disabled-default control and independent empty builds observed exit 83 or a real linker error. A native-only installation change with no Rust edit left a normally fresh unit alone.

## Disposition

On #72, the old shortcut admitted only a rebuilt ordinary self rlib with unchanged public identity and all remaining dependencies fresh. The original generic relink mechanism already covers every member of that set and still runs the real linker. Retiring or superseding that historical proposal removes the unsafe behavior. #28 was already closed without merge. The independent release fix belongs on the release line. [Cargo #281](https://github.com/astral-sh/ohm-cargo/pull/281)

The optional private commit 15d40ff2940ffcd62acfa412b23099e8efe60e1e directly follows #72 and ports the public-API-aware codegen rule from fd872c053bb1e9dcde722cf90a05a7cb8335dd32. A real public type rename made both #71 and #72 fully compile an unaffected integration test. The port reused its codegen through rustc link-only, ran rust-lld, and an independent native Rust caller returned 29. Reverting returned 17. A test actually using the old type failed with E0425 on warm, repeat and empty builds. Separate ordinary Rust cases checked 1, 2, E0308 and restoration. Both declared-provider regressions and all seven fixed-source native tests passed. Three changed expectations failed on the original #72 binary in the same harness. This is independent functional evidence for a different optimization. No timings were collected.

The private port does not salt old Cargo fingerprints. Changing only the Cargo executable at a stable physical path left previously poisoned historical targets falsely fresh twice with identical rustc and workspace state. The next genuine library edit corrected the valid case to 29 and made the malformed case fail. The later scoped migration in 2447f7f4 is independent of this historical port.

## Verification

Run `python3 -IB verify.py` and `sha256sum -c SHA256SUMS` from this directory. The verifier reconstructs physical rustc modes and output-selected native linkers from 156 primary Cargo invocations, 20 separate provider preparations, and compares 10 traced executions of the same built-in testsuite. Full hashes bind the physical and portable versions of 907 streams. Local prefixes in fixture/build logs are normalized. The checked-in tests retain the SHA of each successful original execve and its role. Native histories include the full normalized successful command vectors. The optional source patch applies directly to 0d46e411.
