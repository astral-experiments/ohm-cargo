# Measuring ways to reduce the cost of a second branch

These are separate research prototypes. Ohm Rust #274 retains its ordinary incremental files. For each prototype, two counterbalanced pairs switched between the historical Ruff parser branches, using a fresh installation per arm on ext4. Each return ran both rustcs, and each resulting executable matched the corresponding empty build. The storage measure counts the entire target and build directories, with hard links counted once. [Current PR footprint](..)

| Experimental behavior | Return to parent branch | Return to feature branch | Complete storage on return, parent / feature |
| --- | ---: | ---: | ---: |
| Compress all large private files in the older session | 1.95×, 2.22× | 2.01×, 1.82× | +7.4% / +24.4% |
| Compress only the two large tables in both sessions | 2.07×, 2.78× | 2.34×, 2.74× | −4.3% / +7.4% |
| Compress the same two tables with rustc’s existing flate2 library | 2.41×, 2.62× | 2.06×, 2.40× | −3.1% / +8.8% |

The first two rows use lossless Zstandard at level 1 and include the time to encode, restore and verify the data. The first row brackets the actual native Cargo command with those operations. The second row runs the codec inside the actual compiler commands after a second checkout exists. It restores only the selected dependency graph and query cache, including hardlinked aliases. On the first visit to the new branch the second row took 0.33 and 0.82 s longer. An unchanged Cargo command invoked no codec. [First trial](older-files.json) · [Second trial](two-tables.json)

The third row used flate2 1.1.9 with its fast zlib encoder, called from the same real compiler entry point. The complete outputs used 279 MiB on the parent and 281 MiB on the feature branch. The two first feature visits cost an additional 1.07 and 0.64 seconds. Including the immediately following return, the first visit and return together were 1.31× and 1.38× faster. [Third trial](two-tables-flate2.json)

We also reversed and reapplied a real Ruff grammar edit after visiting both branches. With the guarded compiler held fixed, the flate2 prototype added 0.34–0.61 s on each of four same-branch edits. Each edit restored and re-encoded two tables in the one parser compiler. An unchanged Cargo command invoked no codec. [Same-branch edits, native outputs and paired costs](same-branch-edits)

The prototypes use private serial compilation directories. An in-compiler implementation needs to support concurrent sessions, interrupted writes and existing caches. These four installations per row screen alternatives for a larger comparison. Run the verifier locally to recompute every paired return and disk ratio.

```sh
python3 -IB verify.py
```

## Twelve-pair storage and return-time experiment

A separately registered cohort repeated the second prototype, using Zstandard for the dependency graph and query cache on both branches. Six pairs ran the parent first and six ran the prototype first. Every pair used new Cargo target and build directories. The elapsed time includes all compression, restoration and integrity checks performed in the real compiler invocations. Each return ran the AST and parser compilers. The two branch executables matched their independent empty references.

| Visit | Parent median | Prototype median | Median paired speedup | Simultaneous median interval | Complete storage, parent → prototype |
| --- | ---: | ---: | ---: | ---: | ---: |
| Return to parent | 8.65 s | 3.16 s | 2.70× | 2.52–2.85× | 288 → 276 MiB |
| Return to feature | 8.65 s | 3.20 s | 2.67× | 2.59–2.89× | 258 → 277 MiB |

The first visit to the feature branch took 8.39 → 8.99 s. The first visit plus its next return together took 16.91 → 12.17 s (1.40× median paired). The registered thresholds were a simultaneous lower bound above 2× for both return directions and at most 10% more total storage on every return. The trial met those thresholds. [Registered plan and all paired observations](twelve-pairs.json)

### Run the Zstandard experiment

Run the following from the top of the branch-switch benchmark directory on Linux with the two original matched SDKs, Rustup, GNU coreutils, a populated offline Cargo home, and the `zstd` executable. Choose a fresh output directory. The script creates a private checkout and private target and build directories there. The Rust wrapper only enters the codec for the two named candidate compiler processes. Its manifests and packed files stay in this private experiment.

```sh
python3 -IB replay.py --parent-sdk "$PARENT_SDK" --candidate-sdk "$CANDIDATE_SDK" \
  --workflow build --pairs 12 --jobs 4 --offline --pack "$RUFF_PACK" \
  --compress-incremental-tables --out "$NEW_OUTPUT"
```

Each successful visit records the complete deduplicated physical sizes in `allocated.json`. The `table-visits` subdirectory records which compiler restored and encoded each graph. Finished paired timings are written to `summary.json`. [Compiler wrapper and codec](replay)

Two fresh paired installations exercised this replay entry point in opposite orders. All 24 allocated-size records reconciled with the complete directories, and both branch executables matched their independent clean builds. The four return ratios ranged from 2.36× to 2.77×. These observations qualify the public script separately from the twelve-pair sample. [Replay source hashes and qualification](replay-qualification.json)
