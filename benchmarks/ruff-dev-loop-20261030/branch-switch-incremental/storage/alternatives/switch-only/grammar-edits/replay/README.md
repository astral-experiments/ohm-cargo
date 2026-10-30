# Replay the ordinary same-branch Ruff grammar edit

Use Python 3.11 or later, Linux x86-64, GNU coreutils, Git, and rustup's cargo and rustc shims. Supply a local Ruff checkout containing the historical revisions, the two already-built SDKs, and a populated sparse Cargo registry. Allow roughly 8 GiB in a fresh private output directory for the retained stores, compiler banks, private registry, and logs. All Cargo commands use the offline lockfile and native-input checks from the selected Ohm Cargo.

```sh
python3 -IB replay-same-branch.py \
  --ruff /path/to/ruff \
  --raw-sdk /path/to/c9119d267c98-sdk \
  --switch-sdk /path/to/08d49cba6aac-sdk \
  --registry /path/to/cargo-home/registry \
  --out /path/to/new-reviewer-run
```

The runner uses a private Git object database, branch refs and index. It reads the supplied checkout only as an object donor. For every call it verifies the actual HEAD, staged tree, grammar source bytes, and lockfile. It copies the two real launchers and drivers once, then hard-links each role's fixed inode into the same visible SDK path for all its installations. Cargo, Wild and the target standard library must match. All builds use *cargo +ohm build -p ruff_python_parser --locked --offline -j4 --message-format=json* with the experimental branch cache enabled.

Six independent empty references cover A, B and the changed B grammar for each role. Each of four subsequent installations starts with empty target and shared stores. It visits A, B, A, B, changes and restores the #28233 grammar twice on the same B branch, then runs B unchanged. The two blocks use opposite compiler orders. Every row requires the 97 genuine typed artifacts and expected dirty roster. A freshly linked reader checks a valid and an invalid parse, the observed sign-pattern verdict and the actual Expr size. The reader ELF must match its clean reference in full. The two final summary lines per block distinguish the first hot grammar edit from the next three changes. Detailed per-call seconds, physical allocated bytes, command output, SDK provenance, retained stores and clean executables remain in the output directory.

For an inexpensive source and argument check run these commands.

```sh
sha256sum -c SHA256SUMS
python3 -IB check-recording.py
python3 -IB replay-same-branch.py --ruff /path/to/ruff \
  --out /path/to/new-source-only-check --check-sources-only
```

The adapter's own exercised smoke used the real historical changes to reconstruct all nine Git states in a private sparse checkout. The donor's HEAD, branch, index contents and metadata stayed unchanged. A separate mechanical check passed six complete Cargo and downstream-rustc argument lists from the measured raw streams, spanning all three states, both drivers, cold, first dirty, restore and unchanged. The native grammar receipts include three distinct matching complete executable hashes. The portable native replay is provided for independent use. The measured 68 native Cargo builds used the original instrumented study harness. See *smoke.json* for the exercised scope.
