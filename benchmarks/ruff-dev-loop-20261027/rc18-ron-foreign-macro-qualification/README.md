# Why unchanged Ruff test compilation rebuilds Ron

This is the prerelease Linux R2 rehearsal, with Cargo `7181bfa6256f94da142f80fd6af09cee02ec2c78` and Rust `9828b82f475f18bf9077ee25f36de43d4fec8277`. The active files from both SDK trees were independently SHA-256 checked before the ordinary controls. The transferred bin and lib directories contain 78 active files. Rust's `compiler/` is the same Git tree as the final release source. The published package is a separate qualification.

At Ruff `93526150df078af7dd8fc4226cdcc469539d2001`, each of two genuine unchanged 619-unit workspace test builds compiled registry `ron 0.12.0`, started 50 native Rust link-only jobs and ran 50 real stock Wild processes. Ron’s Rust command line was identical across cold, unchanged, a ty_server source edit, restoration and the final unchanged command. The ordinary opt-in to Ron comes through ty_project’s Insta dependency. Ron has the `default,std` features.

The actual 3,720-byte Cargo fingerprint contained 20 entries. Index 11 was the foreign-span prerequisite, status 0, with no file checksums or environment entries. The four entries in Rust's textual dep-info for that path include its targets and dummy rule. An independent portable BLAKE3 implementation verified the stored checksum and rejected a one-byte status change. Rust records the joined span of an imported source file. Cargo treats any authenticated observer marker as a missing prerequisite. [Rust span join](https://github.com/astral-sh/ohm-rust/blob/a4fa11bcd38280639cb94daacc125472657db6c3/compiler/rustc_expand/src/proc_macro_server.rs#L803) and [Cargo fingerprint](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/compiler/fingerprint/mod.rs#L1796).

The 2,107,440-byte rlib remained identical. All three 1,442,543-byte standalone Rust metadata files have the same root hashes and 3,240 stable definition keys. Five late-allocated definition numbers differ for opaque lifetimes on the return types of the Map iterators. Their stable keys still bind to the identical source positions. This is distinct from Cargo's missing prerequisite. The direct extern file digests in `workspace.json` were read from the retained target. The historical traces establish the argument spellings, with hashes taken later.

## Native controls

The ordinary workloads used an authenticated directory source containing all eleven locked packages, no compiler wrappers, and a private source and target per fixture. All output is observed in a real independent Cargo caller. No Ruff source was edited.

- A change to the real bitflags exported macro recompiled bitflags and Ron. The caller returned 3 instead of 2, agreed with a separate empty build, and returned 2 after the source was restored.
- A change to the existing Serde newtype derive changed Ron’s own serialization from `Extensions("IMPLICIT_SOME")` to `ChangedExtensions("IMPLICIT_SOME")`. The edited and restored programs each matched the SHA-256 of their respective independent cold executable.
- In a separate same-path control, the original Serde source remained in place and Cargo reported its proc-macro binary fresh. Two formerly compiled Serde DSOs were padded to the same ELF file length and written alternately to the same inode while preserving mtime. Ron still produced the correct changed, repeated and restored outputs. Ctime and full file digests differed. Each arm began with the corresponding library at rest.
- A stable Rust proc macro compiled alongside genuine Serde/bitflags joins read 17 or 29 from an external Unix-socket server. The socket identity and timestamps, Cargo input paths, source and macro images stayed fixed across the warm commands. The socket is absent from both dep-info files. Both states matched independent empty builds. This exposes an ambient input in the constructed macro. Serde's observed native stack instead reached `getrandom` through Rust's initialization of hash-table keys. The observed Serde implementation uses its sets for membership tests and emits bounds in parameter order. The syscall selection and unwound stacks are descriptive, including the authentic socket positive control.

## Reproduction

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py`. All observed process-trace hashes, structured phase results, source versions and program digests are in `native.json.gz`. The bulk traces and Rust metadata bodies remain with the original studies. The verifier validates the commitments and observations in this packet. `workers/verify-record.py` verifies an independently supplied raw Rust observer record against BLAKE3's portable C distribution.

For a fresh Linux execution, provide a new empty result directory, a compatible physically installed Ohm SDK, an unmodified checkout of the pinned Ruff revision and the registry cache containing its locked crates.

```sh
python3 -IB workers/ordinary.py --root "$RESULT" --sdk "$SDK" --ruff "$RUFF" --archives "$REGISTRY_CACHE"
python3 -IB workers/serde-upstream.py "$RESULT"
python3 -IB workers/ambient.py "$RESULT"
python3 -IB workers/ambient-v2.py "$RESULT"
python3 -IB workers/expansion-effects.py "$RESULT" "$RESULT/serde-stack" ron
python3 -IB workers/expansion-effects.py "$RESULT" "$RESULT/socket-stack" socket
```
