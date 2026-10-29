# Generated Ohm cache writes through final symlinks

We ran 84 ordinary offline Cargo commands across six private Linux toolchain configurations. The public Linux releases 1.99.0-17, -18 and -19 and the release-profile parent at 5394ce88 overwrote separate files owned by the same user. The correction at 8dc33c9c preserved their bytes and inodes, using both the same source-built Rust compiler as the parent and the publicly distributed -19 compiler.

| Generated entry | Reproducer |
| --- | --- |
| Public API hash | Place a symlink before changing a library's public return type. |
| Workspace resolve cache | Place a symlink at the resolve cache before the next build. |
| Compiler message provenance | During a real library edit, place the symlink immediately after Cargo removes its previous record. |
| Early integration-test check hint | During a real test check, place the symlink immediately after Cargo removes its previous hint. |

The two preinstalled cases rebuild a library and its binary consumer. The executable changes from 17 to 29 and an unchanged build runs it again. The provenance case returns 17, 29 and 31 and repeats 31 on a fully fresh graph. For the two interleaves, an ordinary same-user process watched a private directory through inotify, without wrapping Cargo or rustc. A separate preinstalled-link control in each of those histories preserved the unrelated file on all images. The final commands for every arm reported all selected units fresh. Both corrected writers replaced the entries created before compilation, and both postcompiler writers replaced the entries created during compilation. Each resulting record contained the expected generated format.

Run `python3 -IB verify.py` to check the published native results. To replay one installed toolchain use `python3 -IB probe-generated-cargo-cache-writers.py /tmp/new-api /path/to/sdk --case public-api --expect protected` or substitute `resolve`. For the phase-sensitive cases use `python3 -IB probe-postcompile-cache-writers.py /tmp/new-provenance /path/to/sdk --case provenance --expect protected` or substitute `check-hint`. Use a new owned directory for each attempt. Select `--expect follows` on each affected release. Each supplied SDK needs bin/cargo, bin/rustc and its matching Rust libraries. Use the rustup Cargo proxy on PATH.

The release-profile parent and candidate have the same compiler, profdata, 239 independently verified Rust externs, and 335 native linker files. All recorded Cargo stdout and stderr digests were checked against the original command streams before export.
