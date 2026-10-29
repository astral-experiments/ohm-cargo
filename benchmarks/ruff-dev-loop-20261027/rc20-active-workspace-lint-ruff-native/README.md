# Reusing workspace resolution after an active Ruff lint edit

Ruff removed a workspace-wide allowance for `clippy::large_stack_arrays` in commit `3edca130e22b`. The historical commit changed only `Cargo.toml`. Reversing and restoring those three lines on Ruff `93526150df07` changes the actual rustc arguments inherited by `ruff_text_size` and its serde test. Two matched release-PGO Cargo binaries used the released Linux x86-64 Ohm `-18` compiler, driver, standard library and Wild. The candidate changes how Cargo fingerprints workspace resolution. [Historical Ruff edit](https://github.com/astral-sh/ruff/commit/3edca130e22b2aba1d0cfe263e3f6a6679e166cc)

On either transition the parent resolved the full workspace. The candidate reused that resolution while running the same compiler and linker work. Every command used a fixed environment across the edit. `check` sometimes issued two resolver requests. We count the full resolver and cache hits separately in each complete debug stream.

| Historical lint transition | Current-source compiles per arm | Stock Wild links per arm | Independent empty-build comparison |
| --- | ---: | ---: | --- |
| `check -p ruff_text_size` | 1 | 0 | Same selected metadata and consumer metadata |
| `build -p ruff_text_size` | 1 | 0 | Same linked consumer bytes and output `17 29 12` |
| `test -p ruff_text_size --features serde --test serde --no-run` | 2 | 1 | Same complete serde ELF and three passing named tests |

The suite also inserts a real unreachable `pub` item. Changing Ruff’s inherited `unreachable_pub` from `warn` to `deny` makes the first edited check fail at the same source span as an independently empty build. Restoring `warn` succeeds. An independent type error yields the matching `E0308` on the warm and empty checks. All 18 immediate repeats across the two arms use zero compilers and linkers. The 14 test executables run all 42 individual test cases outside timing.

The machine-readable product comparison retains every difference. Within either arm the incremental and independently clean root `.rlib` differ on the package and serde build, including after restoration. Across the two physical Cargo images, eight of 24 typed intermediate serde products differ. Their compiler arguments contain different per-toolchain store directories. The complete test executables and externally linked caller outcomes match. `products.py` joins all products on package, target, target kind and file extension before comparing their bytes.

`streams.json.gz` contains the Cargo JSON, resolver log, split and completed kernel execs, harness inventory, verdicts and product hashes for all 56 commands. `raw-file-index.json.gz` includes the digests before and after replacing the private checkout, SDK, rustup proxy and registry names. `source-tests.json` retains the original regression’s outcomes. The focused unit and candidate integration tests pass. The parent fails the restored cache-hit assertion. The final test at `fd7269b3bb52` also rejects a full resolve followed by a cache hit in the same check. Against the exact release-PGO images it fails on the parent’s first lint transition and passes on the candidate. The production source blob is identical to the measured candidate. `subjects.json` binds the two measured Cargo sources and images. The measured parent and direct PR parent differ only in the test file. The `reviewer` directory is a separate full execution of the published command at a different literal workspace path. All 56 verdicts, source hashes, compiler and linker counts and named test results matched the original execution.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
python3 -IB products.py
python3 -IB verify.py --captures reviewer
python3 -IB products.py --captures reviewer
```

For another execution, use an unmodified Ruff checkout at `93526150df078af7dd8fc4226cdcc469539d2001`, an offline Cargo home already containing its locked dependencies, the distributed `-18` SDK, and the two Cargo executables. `WORK` and `REPORT` must be distinct, new paths beneath existing directories. The Linux runner uses `sudo -n unshare`, a private three-GiB tmpfs and read-only donor mounts. It drops privileges before running any project executable. Set `CARGO_CHECKOUT_PARENT` and `CARGO_CHECKOUT_CANDIDATE` below to the two Cargo executable paths. The recorded images are authenticated by default. For two independently source-built images, pass their own SHA-256 digests as `--control-sha256` and `--candidate-sha256`. The report records both actual digests and full version strings.

```sh
python3 -IB replay.py --check-source "$RUFF"
python3 -IB replay.py --checkout "$RUFF" --sdk "$SDK" \
  --control "$CARGO_CHECKOUT_PARENT" --candidate "$CARGO_CHECKOUT_CANDIDATE" \
  --cargo-home "$OFFLINE_CARGO_HOME" --work "$WORK" --out "$REPORT"
```

The native witnesses ran separately from ordinary wall samples. The timing registration also includes an independent locked consumer and archive witness. [Registered wall-time protocol](https://github.com/astral-sh/ohm-cargo/tree/538b5eb2ac5cee08f3e6a3830041b4515902cd92/benchmarks/ruff-dev-loop-20261027/rc20-active-workspace-lint-wall-plan) · [Untimed resolver and timer admissions](https://github.com/astral-sh/ohm-cargo/tree/95c95319e6aa5ada6586c7d781542f91c0b76a8d/benchmarks/ruff-dev-loop-20261027/rc20-active-workspace-lint-wall-admission)
