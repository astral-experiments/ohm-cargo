# Candidate treatment for pending metadata dependencies

On the release parent the reader committed its public API as unchanged while provider metadata was still provisional. Candidate `b3360c5eda186845b9a2ba6e5330a97c07d4acf2` treats a pending metadata dependency conservatively. Under the very same forced order, Cargo kept the reader's real invocation timestamp, 213,005,285 nanoseconds later than the final provider generation. Both following unchanged checks were fully fresh. The release parent ran the real reader compiler on the first unchanged check. The exact literal rustc argv, complete source inputs in this fixture, and full before/after metadata bytes for both crates match across both Cargo images and both forced schedules.

| Check | Parent | Candidate |
| --- | --- | --- |
| Both source edits, provider-first or consumer-first | 2 actual rustcs | 2 actual rustcs |
| First unchanged check after consumer-first publication | 1 actual rustc | 0 actual rustcs |
| Second unchanged check after either order | 0 actual rustcs | 0 actual rustcs |
| Real incompatible provider return type | Warm and empty reader E0308 | Warm and empty reader E0308 |
| Trait implementation removed behind unchanged reexport | Warm and empty caller E0277 | Warm and empty caller E0277 |
| Trait implementation restored | Warm and empty success | Warm and empty success |
| Single missing reader output | 1 actual reader rustc | 1 actual reader rustc |
| Provider fails its own type check twice | Both fail, same E0308 as empty | Both fail, same E0308 as empty |
| Repair after failed provider | Warm and empty success, repeat fresh | Warm and empty success, repeat fresh |

The packet binds a matched PGO control Cargo, the separately built **debug** candidate Cargo, the actual official -18 Rust executable and driver, literal per-unit post-Cargo argv, actual successful rustc execs, complete Cargo outcomes and current artifact hashes. Both the initial and second in-place checks of the parent's previously settled seed were fresh under the candidate. The candidate binary retains the parent version display. Its candidate-only diagnostic text is present in the actual forced-order Cargo log and its source, executable SHA-256 and producer receipt are in `identity.json`.

There were 21 primary candidate calls, 6 additional failed-provider or repair checks on the candidate, and 6 matched additional controls on the parent. The parent’s original 39-command packet remains separately sealed. These are structural and behavioral checks. The metadata timestamp gap is not a command-duration measurement. The host’s normal original and slower traced Ruff runs alone cannot identify which order actually occurred in an earlier untraced run.

Run `python3 -IB verify.py`. The fixed and parent native controls have individual raw stdout, stderr and native trace digests, per-unit process IDs and argv with the private fixture prefix aliased. The same-path parent evidence is included for the independent cross-image comparison. The current sources for the barrier and independent controls are in the paired parent packet; the additional receiver and failed-provider cases are in `reproduction/`.
