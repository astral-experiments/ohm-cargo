# Opting into an alternate incremental session

After a serial compile, Rust `c9119d267c98` keeps one finalized incremental session per crate by default. Garbage collection skips sessions held by active readers and can remove them on a later run. Setting `-Zohm-branch-cache=yes` lets rustc keep a session from one other Git checkout when Ohm’s native-input checks are enabled. The stored files use the ordinary incremental format. [Compiler source](https://github.com/astral-experiments/ohm-rust/commit/c9119d267c9843f0fb5dcbc1cc05653eac6051e3)

Two independent pairs compared the new compiler with its parent using ordinary Cargo defaults. On return to the Ruff parent branch the complete target and build directories used 288 MiB with both compilers. On return to the feature branch they used 258 MiB with both. Every visit kept exactly one session per affected crate. The maximum difference across these four return comparisons was under 0.1 MiB. Both complete executables matched their independent clean builds byte for byte on both compilers. These pairs check default behavior and disk allocation.

Two more pairs compared opting in and out on the same compiler build. Both modes shared all 55 native SDK files, Cargo and Wild. Each pair used a fresh target and build directory in both orders across the cohort. The earlier screen installed copies of the same compiler bytes before independent runs. The fixed-installation runner also holds the device, inode and ctime of Cargo, rustc and the driver constant throughout the cohort.

| Return | Speedups in the two pairs | Complete bytes on disk, default → opt-in |
| --- | ---: | ---: |
| Ruff parent | 3.21×, 3.44× | 288 → 380 MiB |
| Ruff feature | 3.47×, 3.37× | 258 → 382 MiB |

Both AST and parser rustcs ran on every return. All four sampled installations returned the clean branch-specific executable. The first pair in each cohort also ran the invalid edit and its repair on both arms. Each of these four controls returned Cargo 101 with E0308, then built successfully and recovered the feature branch’s expected native behavior. [Error and recovery records](negative-controls.json) The test compiler also passed its complete four-test incremental unit suite, the seven-invocation option regression and twelve invocations covering externally read native assembly. [Compiler qualification](compiler.json)

A separate nine-command ordinary Cargo fixture used shell `RUSTFLAGS` and project `.cargo/config.toml`. All real compiler invocations used the same incremental crate directory. The finalized session counts were 1, 1, 1, 2, 2, 2, 1, 1 and 1. The eighth Cargo command recovered a fully fresh executable returning 29 with zero compilers and zero linkers. A real source edit then returned 41 with one compiler and one Wild link, keeping one session. [Native commands and outcomes](cargo-config.json)

## Reproduce the two-pair screen

With the compiler at the revision above installed as `ohm`, a normal opt-in build uses this command.

```sh
RUSTFLAGS=-Zohm-branch-cache=yes cargo +ohm build -p ruff_python_parser
```

From the top of this benchmark directory, use the same native SDK path for both arms of the option comparison. Choose a fresh output directory and a populated offline Cargo home. The historical Ruff pack may be omitted when GitHub is available. The helper reconstructs the measured runner and checks its source digest before invoking Cargo.

```sh
python3 -IB opt-in/run.py --screen --parent-sdk "$OPT_IN_SDK" --candidate-sdk "$OPT_IN_SDK" \
  --same-sdk --enable-retention --workflow build --pairs 2 --order-seed 202610300651 \
  --offline --pack "$RUFF_PACK" --out "$NEW_OUTPUT"
```

For the default comparison, supply the parent SDK to `--parent-sdk`, omit `--same-sdk` and `--enable-retention`, and use seed `202610300653` with another fresh output directory. Omitting `--screen` selects the fixed-installation runner. Run `python3 -IB opt-in/verify.py` to recompute the published comparisons.

## Fixed compiler installation

Each workflow below used twelve additional fresh pairs and six pairs in each order. Cargo, the rustc executable and its dynamic driver kept the same device, inode and ctime across both option settings and all independent targets. The timer covers ordinary native Cargo. The intervals use simultaneous 95% coverage for the two return directions. Disk figures count both complete Cargo directories and deduplicate hard links.

| Workflow | Return | Default median | Opt-in median | Median paired speedup | Simultaneous interval | Default → opt-in disk |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `cargo build` | parent | 8.92 s | 2.76 s | 3.26× | 3.18–3.45× | 288 → 380 MiB |
| `cargo build` | feature | 9.03 s | 2.72 s | 3.33× | 3.12–3.61× | 258 → 382 MiB |
| `cargo check` | parent | 6.72 s | 2.05 s | 3.29× | 3.08–3.58× | 184 → 242 MiB |
| `cargo check` | feature | 6.90 s | 2.05 s | 3.34× | 2.97–3.67× | 173 → 243 MiB |

The first visit to the new branch and its following return form a shorter history than repeated branch switches. Their combined median paired speedups were 1.53× for `cargo build`, 1.55× for `cargo check`.

Each saved native reader matched the full independent empty-build executable for its branch. Replay seed `202610300701`. [All pairs](option-build-12-pairs-elapsed-202610300701.json.gz) · [Order-statistic intervals and exact tests](statistics-option-build-12-pairs-elapsed-202610300701.json) · [Independent native or type verdicts](verdicts-option-build-12-pairs-elapsed-202610300701.json.gz)

Across 126 visits, including clean references and repairs, the correctly sized type probe passed and the contradictory size failed with E0308. Replay seed `202610300702`. [All pairs](option-check-12-pairs-elapsed-202610300702.json.gz) · [Order-statistic intervals and exact tests](statistics-option-check-12-pairs-elapsed-202610300702.json) · [Independent native or type verdicts](verdicts-option-check-12-pairs-elapsed-202610300702.json.gz)

To rerun one fixed-installation cohort, use the option command above, omit `--screen`, pass `--pairs 12`, and select its published workflow and seed.
