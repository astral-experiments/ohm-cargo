# Two observations of generated Ruff inputs on Ohm 1.99.0-18

The ordinary command was `cargo +ohm build --locked --offline -p ty_vendored` on Linux at Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. Seven warm runs had a 217.66 ms median on an AMD EPYC Genoa host. Bounds were 213.32–241.72 ms, including the private namespace launch. Two additional traced commands executed only the rustup proxy and installed Cargo. A separate JSON build confirmed all 182 compiler artifacts were fresh. The emitted rlib and standalone rmeta matched the starting bytes on every unmodified command. This one-package workflow has its own denominator.

| Physical work on one genuine fresh build | Observations |
| --- | ---: |
| Worktree policy markers | Three rewrites and 21 syscalls |
| Prior build-script stdout | 23 files, 50 opens, 326,100 bytes |
| Prior build-script root-output | 23 files, 48 opens, 7,354 bytes |
| Generated output data | 7,918,933 distinct bytes, read twice |
| Cargo instructions attributed to worktree script-result hashing | 31,657,779 of 313,383,176 (10.10%) |
| Cargo instructions in all ordinary source checksum reads | 35,458,284 (11.31%) |
| Cargo instructions in all calls to prev_build_output | 2,856,759 (0.91%) |

Cargo first hashed both Unicode tables, then read both against rustc's dep-info. It later did the same for the compressed typeshed ZIP. The script-result digest includes the parsed build output, raw stdout, path/type/mode/size information and generated content. It read each generated file through EOF in 16 KiB requests. All three corresponding rustc depfiles recorded an independent raw BLAKE3 with the exact length. The fingerprint check read the files in 64 KiB requests. Both physical traces retained the exact order, including the two distinct opens and closes for each file. Source links point to the released Cargo commit. [Script-result digest](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/compiler/fingerprint/worktree.rs#L39) · [Dep-info check](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/compiler/fingerprint/mod.rs#L3231)

## A changed file between the two opens

A test interposer changed exactly one private path immediately before Cargo's second open of the 5,577,690-byte ZIP. The valid replacement changed two timestamp-field bytes, at offsets 10 and 5,519,002, in the same ZIP entry’s local and central headers. File size, nanosecond mtime and mode matched. The complete entry roster and every byte of the selected 18,553-byte `stdlib/functools.pyi` remained equal. The preselection also retained both ZIP hashes and the complete bytes each compiler artifact contained.

| ZIP seen by the script check | ZIP seen by the consumer check | Actual outcome |
| --- | --- | --- |
| Original | Original | All 182 artifacts fresh |
| Original | Changed | Only ty_vendored dirty. New rlib held the changed ZIP twice, new rmeta once |
| Changed | Original | Only ty_vendored dirty. New rmeta equaled the original byte-for-byte |

In the first direction, a subsequent normal build with the changed ZIP produced the same changed rmeta. Restoring the ZIP reproduced the original rmeta and all three original embedded ZIP copies. Rlib hashes from forced Rust compiles varied across repetitions; the packet records every hash and uses complete embedded ZIP bytes for their product check. The opposite directions used separate workspaces cloned from the same settled history. If Cargo used the script check's digest to skip the consumer read it would retain stale generated content on the first transition. Dropping the script check in favor of the later consumer checksum would change the actual generation/freshness decision in the reverse transition.

## How much preserving both observations costs

The bounded model reads the same real files twice in both arms. The current-style model feeds raw bytes to the script tree on the first pass, then computes each raw BLAKE3 on the second. A candidate model hashes each first-pass file into a leaf and keeps an owned byte copy. During each second read it compares the actual bytes against that copy. On a mismatch it authenticates the complete second stream, including the prefix already compared. Releasing both Unicode buffers before the ZIP limits peak retained content to 5,577,690 bytes. A product implementation would require a versioned file-leaf recipe, conservative fallback for unsupported or oversized files, and a bound on retained memory. The C model measures payload operations on the three selected files. It omits other output metadata and receipt migration.

Each genuine input replacement produced the same raw BLAKE3 in both models. In the 24 balanced adjacent pairs, the two streaming hashes took 9.215 ms median and the retained-copy model took 10.689 ms. The paired median additional cost was 1.490 ms, with 1/24 favorable. Median minor page faults were 24 for streaming and 1,959 with the retained copy. Both arms read 15,837,866 bytes. This product-free native screen used one idle core, fresh processes and the published C implementation from the exact blake3 1.8.5 crate locked by Cargo. The whole-command time above describes the released unmodified Cargo. The screened design did not qualify for a product change.

## Existing optimization and controls

Restoring the normal cache directory ownership in a private user namespace cut the Git file-list attribution from 66,125,565 to 11,520,986 instructions on the JSON comparison. In the initial namespace, both `/` and `/home` appeared as uid 65534, causing the released cache's trusted-ancestor guard to refuse Git and registry receipts. The corrected layout preserved the site’s read-only Cargo configuration, original effective path spellings, and euid/root ownership compatibility. The existing Git optimization already addresses the substantial SHA-1 cost there. The complete plain command used 11,501,994 instructions in file listing. [Verified index reuse](https://github.com/astral-sh/ohm-cargo/pull/249)

The 2026-10-28 snapshot covered all 228 Cargo and 220 Rust pull requests, plus 283 live Cargo and 312 live Rust branches. The 287 distinct Cargo branch/PR heads were checked for the current and historical script-fingerprint source file. All versions with the four content-hashing routines had byte-identical function bodies for those routines. The recorded related proposals include seeded script results, marker safety, build-script parsing, checksum prefetch and previously verified Git indexes. [Worktree seeding](https://github.com/astral-sh/ohm-cargo/pull/101) · [Script generation time](https://github.com/astral-sh/ohm-cargo/pull/256) · [Parsing prior stdout](https://github.com/astral-sh/ohm-cargo/pull/177)

Run `python3 -IB verify.py` from an unpacked copy for offline verification. The JSON files contain all 48 native slots, the two-direction release controls, independent tool/trace digests, incoming and outgoing instruction counts, and the exact selected depfile commitments. `reproduce/` retains the narrow acquisition and model sources, including the campaign’s private layout. The three generated inputs can be obtained by building Ruff at the specified commit. Their required SHA-256 values are in `selected-inputs.json`. Historical trace and profile hashes commit the raw data retained privately. The first profiler stopped during Cargo startup with zero artifacts. The first trusted-namespace setup omitted site registry configuration; the first raw ZIP oracle expected one rlib copy; and the initial native model preflight found multiple historical output directories. `excluded.json` retains those setup failures. None supplied a scored native observation.
