# Full rustc instructions for Ruff’s PythonVersion edit

A cached MIR query reduced the guest instructions of the whole dirty rustc process on an ordinary `cargo build -p ruff_python_ast`. This packet covers one historical source edit in both directions, using optimized stage1 compilers on x86-64 Linux. It has no whole-Cargo elapsed-time or release-PGO estimate.

| Source change | Parent median Ir | Candidate median Ir | Median paired reduction | 95% interval | Favorable pairs | Exact two-sided p |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| Apply the historical change | 7,660,415,260.5 | 7,448,738,088 | 2.7733% | 2.7383%–2.8058% | 12/12 | 2/924 |
| Restore the parent source | 7,659,553,019.5 | 7,449,626,979.5 | 2.7458% | 2.7160%–2.7782% | 12/12 | 2/924 |

Ruff commit `93526150df078af7dd8fc4226cdcc469539d2001` provided the checkout. Both full versions of `crates/ruff_python_ast/src/python_version.rs` came from `ef23c9c39eb3029bab0139c3ea7ae6d95c4131e0` and its parent. A separately compiled Rust client printed `3.14 3.14 3.10` with the old source and `3.15 3.15 3.11` with the edit. Its native, profiled and independently clean ELF bytes matched for each state. Cargo reported 39 targets, executed exactly one full compiler and zero stock linkers for the package edit, and executed zero compilers or linkers on the next unchanged command. Both cold histories independently executed 39 compilers and eight linkers. The client link runs separately from the profiled Cargo command.

The Rust parent is `ad005f99d0b51fd62b5c237bc13b31b371a1686e`. Its direct child is `2813724f18d9228075f6086d4f050a147f6e761e`. Their complete 119-command compiler construction vectors, 53 standard libraries, frontend and LLVM were equal. Only the Rust driver differed. Both ran the same Ohm Cargo `84af87848a5a952ba61ae6a2cc5b22da24130200` with its defaults and the same stock Wild. This measures the candidate at incremental format 8 on this exact parent. A separately integrated format-9 compiler needs a fresh experiment. An earlier cohort using different relink-input safety checks contributed zero observations.

### Verify the published observations

```sh
python3 -IB verify.py --self-test
```

The verifier checks every file in the manifest and all 48 chronological observations, then recomputes both stratified bootstrap intervals and both exact randomization tests. Its nine corruption controls cover dropped or reordered slots, a changed count or profile, compiler identity, jobserver and argv, extra no-op work, and a wrong clean verdict. `observations.json` contains each profile’s declared total, the complete raw self-cost sum and the independently reported process total. It also contains original profile, compiler argument, jobserver capture and terminal hashes. `original-scores.json` and `independent-result.json` are the original score and its independently implemented reparse. `query-attribution.json` records exact inclusive call edges from the first registered block in each direction. Inclusive edge costs overlap with other edges and are not the primary endpoint. A second host independently expanded the retained 139,407,067-byte archive, verified all 3,689 files and rescored every raw profile; `sources.json` binds that receipt. The portable projection omits environment paths, executable bodies and full binary profiles.

### Run the experiment on another Linux host

Use x86-64 Linux, Python 3.11+, GNU C, Git, Bubblewrap, strace and Valgrind/Callgrind with `/usr/bin/valgrind.bin`. The kernel must permit ptrace and process_vm_writev on a child owned by the same unprivileged user. Four permitted CPUs, at least 18 GiB available RAM and at least 6 GiB free private storage are required. Each slot starts fresh and preserves its logs; its temporary file tree is removed only on success. A failed slot is kept under `failed/` and ends that invocation. Select a new work directory for a separate run.

Prepare a clean checkout of the pinned Ruff revision (including the historical commit), and a hydrated offline `CARGO_HOME/registry` with its locked index and crate archives. Supply separate complete Linux SDK directories whose compiler source commits are given above, the common Ohm-enabled Cargo and the rustup executable. Complete SDKs need the rustc frontend/driver, std/LLVM, target tools, stock Wild, and an existing `bin/cargo` mount point. Do not install them globally. The compact original result can be verified without either SDK. For independently built SDKs, use identical checkout paths, stage0, LLVM, bootstrap configuration and version stamp for both builds. Build `compiler/rustc` and `library` using `./x.py build --stage 1 compiler/rustc library` on a version-matched bootstrap. Record each source commit and its physical 55-file compiler/standard-library inventory, using the schema below. The adapter independently reopens each file. Independently rebuilt results will vary with the compiler construction and host.

```sh
python3 -IB replay/run.py /absolute/private/new-run \
  --checkout /absolute/ruff --registry /absolute/cargo-home/registry \
  --parent-sdk /absolute/parent-sdk --candidate-sdk /absolute/candidate-sdk \
  --cargo /absolute/ohm-cargo --rustup /absolute/rustup \
  --cpus 0,1,2,3 --limit pair
```

`--limit admission` checks four uninstrumented cross-arm edit/restore histories. `pair` adds a single chronological pair as a smoke test; it has no inferential result. Select `--limit full` on a new directory for the original 48-slot order. For fresh builds add `--allow-rebuilt --parent-product /path/to/parent.json --candidate-product /path/to/candidate.json`. Each manifest must carry the builder-verified `commit`, false `pgo`, `bolt` and `wild_built` flags, and a `files` mapping of all 55 stage1 relative paths to `{"sha256":"…","bytes":123,"mode":493}`. The independently built Cargo must identify the recorded source in `-Vv`; strict mode accepts only the recorded executable digests. A source stamp does not establish the provenance of a compiler by itself. Retain the actual bootstrap build receipt.

The replay uses config-file `[build].build-dir`, matching the registration. The ordinary environment-variable spelling selected compiler-specific output directories on this Cargo and was excluded from the literal-argv cohort. The adapter runs genuine Cargo on each arm under the same view paths and preserves its native jobserver pipe. It compares each dirty profile’s original 119 arguments to both the ordinary native arm and the other compiler. The measurement process is started at the original rustc loader entry by the supplied, checksum-bound `trace.c`, with its original environment and descriptors. `replay/counts.py` reconciles the sole full rustc profile’s Ir total three ways; every complete profile remains under `runs/` on the replay host. No Cargo wrapper is used.
