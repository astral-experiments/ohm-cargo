# Live native library search on 50 Ruff test executables

On unchanged Ruff source, a higher-priority GNU linker script made all 50 preselected executables exit 83. Removing the script restored all 50 original ELF files byte for byte. This ran through normal Cargo, rustc, GCC, collect2 and Wild, with the whole 619-artifact workspace on four Linux x86-64 CPUs.

| Operation | Cargo | Typed artifacts | Full rustcs | Wild processes | Selected programs linked | Program outcomes |
|---|---:|---:|---:|---:|---:|---|
| Four baseline controls | 0 | 619 | 119 | 103 | 50 | 50 original inventories per call |
| Provider insertion, unchanged repeat and forced link | 0 | 619 | 119 | 103 | 50 | 50 exit 83 per call |
| Malformed provider | 101 | 515 | 24 | 9 | 1 | Native script error |
| Remove provider | 0 | 619 | 119 | 103 | 50 | 50 original ELF files and inventories |
| Force with malformed provider | 101 | 514 | 23 | 8 | 1 | Native script error |
| Final removal | 0 | 619 | 119 | 103 | 50 | 50 original ELF files and inventories |

Every successful call reported 433 fresh artifacts and zero cached-codegen compiler launches. The fourth baseline additionally logged Cargo fingerprints. The single selected native job dispatched on each malformed run was `ruff_mdtest/test/mdtest`. Three Wild process families opened the malformed script each time. Cargo then stopped. The 49 unstarted selected jobs have no failure verdict on those two calls.

In the fd-traced valid run, 68 of the 103 genuine Wild families opened both the new script and its object, including all 50 fixed targets. The raw collector independently decoded every returned file descriptor and the contributing worker’s clone ancestry. Each selected invocation had the selected psm build output before `-lgcc_s` on the real Wild command line. All 100 original and altered complete ELFs were reopened and hashed, totaling 7,879,441,416 bytes. All three valid runs produced the same altered 50 hashes. The six healthy runs executed the two notebook cases and the inlay-hints assertion on `ty_server:e2e`, with the full 200-test inventory.

The provider consists of a local x86-64 exit-83 function in `.init_array` and a private GNU `INPUT` script that also names the original GCC script. The system script was never changed. A separate native executable and a real `dlopen` of a shared library each returned 0 with the original input, 83 with the private constructor, and a linker error on malformed input. Both original ELF files returned exactly after removal. Earlier release controls that used a `.preinit_array` executable fixture are separate.

## Subjects and sample history

The checkout was Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. Rust was the source-qualified `ad005f99d0b51fd62b5c237bc13b31b371a1686e` and Cargo was source-built `7277e6cdaba44c43294a07c0661fc8e69fd8e3e7`. The distribution’s stock Wild SHA-256 was `0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5`. The study measures behavior and physical work. It supplies no latency estimates or attestation for a packaged release binary. [Ruff source](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [Rust source](https://github.com/astral-sh/ohm-rust/commit/ad005f99d0b51fd62b5c237bc13b31b371a1686e) · [Cargo source](https://github.com/astral-sh/ohm-cargo/commit/7277e6cdaba44c43294a07c0661fc8e69fd8e3e7).

The original full-workspace donors stayed untouched. A topology-preserving private copy retained 45,543 paths and 4,398 hardlink relationships. Its first independent trial encountered eight additional Rust library invocations and stopped before changing a provider. The next protocol explicitly admitted measured Rust-library variation while requiring the same selected native outputs. In the accepted series all successful visits actually matched the 119 full / 103 native roster. A bind-mount rename returned EXDEV before the first forced call and before moving any inode. The six existing Cargo commands and the zero-command failure were preserved. Five previously unexecuted calls then used the same physical output inodes on the destination’s mount. The dataset binds all three histories.

## Verify or replay

```sh
python3 -IB verify.py --self-test
python3 -IB replay-provider.py \
  --wild "$(rustc +ohm --print sysroot)/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd" \
  --work "$PWD/standalone-provider-fresh"
```

The standalone command above ran against the enrolled stock Wild in a separate fresh directory. It needs Python 3.11+, Linux x86-64, GCC, GNU binutils and strace. Every native link, including each expected failure and the separate loader build, is checked against the supplied Wild's physical file.

For a local independent whole-workspace replay, provide an unchanged Ruff checkout at the pinned commit, an installed Ohm SDK with the desired qualification sources, and a complete offline Cargo registry. Use a new path on one filesystem with ample headroom for the two build stores and traces. The registered host had at least 40 GiB available at warm-copy entry. A new cold replay needs more room. The restoration and trigger checks run through the user's normal toolchain alias.

```sh
python3 -IB replay-workspace.py \
  --ruff "$PWD/ruff" \
  --registry "${CARGO_HOME:-$HOME/.cargo}/registry" \
  --work "$PWD/whole-provider-fresh"
```

This optional adapter starts independently empty, settles twice, records actual Wild invocations and test inventories, then exercises the three valid calls, both malformed calls and the two removals. It keeps every raw local stream. The published H4 data came from the registered warm-copy runner and its dedicated readback. The optional adapter’s typed-target selection was checked against all 50 actual H4 paths. The full optional fresh-clone command was not launched a second time for this publication. Results from another SDK or machine belong to its own local run.

`observations.json.gz` contains all named runtime/ELF outcomes, actual linked and unstarted targets, normalized FD and process counts, and raw stream digests. `collect.py --help` exposes the independent backend for original raw data. `direct-replay.json` comes from the additional genuine run of the public miniature. The offline verifier also rejects corruptions of a descriptor, target membership, failure coverage, restoration, exit status and link count.
