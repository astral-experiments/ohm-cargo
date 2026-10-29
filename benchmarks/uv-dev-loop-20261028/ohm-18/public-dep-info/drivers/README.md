# Cargo executables for the Ohm -18 dependency-file comparison

These are the two new x86-64 Linux Cargo binaries used for the registered post-edit uv workspace comparison. Each trained on 24 non-uv commands. Both use the same linked standard library as the rebuilt control. The source patches apply to Cargo revision `7caf39914da1e28a67744ecbc963a5f26361474d`.

| Arm | Executable and PGO profile | Cargo SHA-256 |
|---|---|---|
| pr269 | [pr269-cargo.zip](pr269-cargo.zip) | `9a4327124d6ea1397895abb22b2d5373355909332e16d755d9979ae948a37b70` |
| head | [head-cargo.zip](head-cargo.zip) | `fd0a7f7faacaf8f1f109a15d08612f5486b8253fe6607976e376d2420ce1f634` |

Extract one archive into an empty directory. Run `sha256sum -c SHA256SUMS`, `chmod +x bin/cargo` and `bin/cargo --version --verbose`. The archive includes the merged LLVM profile, source patch, actual binary audit, training plan and the four driver identities. Both executables report the same release base commit in their version strings. Their SHA-256 values identify the two builds. [Frozen workload and schedules](../amendment-2/) · [All file identities and recovered binaries](detached-verification.json)

The candidate and source-matched control produced identical results on 21 functional observations, including changed dependency sets, escaped names, malformed files, path aliases and multiple crate types. [Recorded functional checks](behavior.json) · [Four Cargo subjects and the rustc/Wild pins](subjects.json)

A process-reader check stopped the first candidate scratch cleanup before any target was removed. The successful retry verified all three owned targets and the original PGO audit again. [Pre-sampling checks and preserved attempts](pre-sampling-custody.zip)
