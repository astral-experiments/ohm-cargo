# Unchanged Ruff package builds with a space in the target directory

On released Ohm 1.99.0-16, each of four unchanged Ruff test builds recompiled `ron` and `ty_vendored` and relinked `ty_project` if the target directory contained a space. The selected test executable remained byte-identical to the cold build after each command. Replacing the space with a hyphen let all 303 units settle fresh.

| Target directory and command | Cargo units reported dirty | Full rustc | Link-only rustc | Wild links |
| --- | ---: | ---: | ---: | ---: |
| Both empty cold states, each | 303 | 304 | 0 | 50 |
| `ruff-target`, first unchanged command | 3 | 1 | 1 | 1 |
| `ruff-target`, each of next three | 0 | 0 | 0 | 0 |
| `ruff target`, each of four unchanged commands | 6 | 2 | 1 | 1 |

The command was `cargo +ohm test --no-run -p ty_project --locked --offline -j4` with Cargo JSON for unit attribution. Its normal test dependencies include `insta` and `ron`. Both states used Ruff 93526150df, the shipped Rust compiler, packaged Cargo, bundled Wild, four jobs and the same canonical workspace, shared directory and registry path. Each cold command started with an empty target and shared directory. There were no Ruff edits, test executions, custom compiler flags, trust overrides or neighboring decoy files. The capture tool ran outside each Cargo invocation.

The released compiler recorded foreign-span use by `ron` in both states. Its Cargo binary-input record stayed incomplete through all four unchanged spaced-path commands. The corresponding record became complete after the first unchanged command on the plain path. These are process counts from successful native executions. Wall time was not scored in this experiment.

Run `python3 -B verify.py` to reconstruct the counts from the original successful execve lines and Cargo messages, compare the SHA-256 of every produced test executable with its preceding output, and check the last recorded observer trailer. The packet contains 2,781 entries. One host-specific registry basename was replaced in 561 entries with a portable alias. Original and portable digests are in inventory.json.gz.

The released wrong-output and FIFO cases use an independent external binary dependency. [Release checksum controls](https://github.com/astral-sh/ohm-cargo/tree/dfcbdbd318e5bfa1154ae1537b02df7bdb2d79b0/benchmarks/ruff-dev-loop-20261027/released16-spaced-checksums)
