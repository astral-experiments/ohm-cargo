# Reproducing the Cargo regressions in the first GNU Ohm 1.99.0-22 distribution

The packaged Cargo reported a deleted type error on two successful checks of repaired Ruff source. It also unlinked files outside the shared cache and private target during collection. Replacing the Cargo executable with the source build at `4591cf45` fixed all three cases using the same packaged rustc, standard library and Wild. [GNU build job](https://github.com/astral-experiments/ohm/actions/runs/41237680370/job/124644935360) · [Distribution artifact](https://github.com/astral-experiments/ohm/actions/runs/41237680370/artifacts/13057710231) · [Proposed release pins](https://github.com/astral-experiments/ohm/pull/225)

| Control | Packaged Cargo `8269d772` | Cargo `4591cf45` |
| --- | --- | --- |
| Invalid Ruff source | Exit 101, `E0308` at line 1240 | Same |
| Repair the source and repeat the check | Both exited 0 and replayed line 1240 | Both exited 0 and reported the live warning at line 1243 |
| Separate clean build of the repaired source | Live warning at line 1243 | Same |
| Shared-cache bind mount after a successful preview | Unlinked the 137-byte file outside the cache, exit 101 | Preserved it and collected the eligible sibling, exit 0 |
| Private-target bind mount after directory enumeration | Unlinked the 43-byte file outside the target, exit 101 | Preserved it, exit 0 |

The Ruff command was `cargo +ohm check -p ty_project --tests --locked --offline -j8 --message-format=json`. The run covered the historical Ruff edit, invalid source, repair, untouched repeat, same-path Cargo upgrade and independent empty builds. Every successful check emitted the same 303-unit graph. The first upgrade rebuilt all 303 units. Across eight visits, the downstream type client emitted identical metadata for the valid input and correctly rejected the wrong input each time. Four complete `ron` metadata files differed. The packaged compiler listed them identically, and renumbering the anonymous lifetime definitions reconstructed each entire file in both directions. [Ruff revision](https://github.com/astral-sh/ruff/commit/93526150df078af7dd8fc4226cdcc469539d2001) · [Historical edit](https://github.com/astral-sh/ruff/commit/32c5cd5daba51d9c3da691c5b43afa6a7a4bb731) · [Per-command observations and hashes](observations.json)

## Two-crate reproduction

With the toolchain under test installed as `+ohm`, run this command from the directory containing the script. It uses two local crates, ordinary Cargo defaults, separate target and build directories, and a fresh offline Cargo home.

```sh
python3 quick_repro.py "$(mktemp -d)"
```

The `invalid` row should exit 101 with `E0308`. The `repair`, `repeat`, and `same-interface-edit` rows should exit 0 with the same `dead_code` warning as `empty`. On the packaged Cargo those three successful commands printed `E0308`. The script keeps the raw Cargo output and the compiler versions in the directory it prints. [Reproducer](quick_repro.py)

The review archive contains stdout and stderr for all 13 actual Ruff commands, the positive and negative type-client diagnostics, the relevant collector syscalls, and both two-crate results. The scratch prefix and registry mirror name are normalized in those streams. The observations file records the SHA-256 hashes of the original Ruff stdout, release artifact and both Cargo binaries. [Review archive](release-observations.tar.xz)
