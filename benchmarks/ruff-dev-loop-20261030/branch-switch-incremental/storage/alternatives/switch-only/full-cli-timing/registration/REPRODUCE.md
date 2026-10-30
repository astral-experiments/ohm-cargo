# Reproducing or checking the study

Python 3.11 or newer and Linux are required for acquisition. The statistical reader uses only Python. To verify the frozen schedule and exercise the exact balanced randomization and rank endpoints, run:

~~~sh
sha256sum -c SHA256SUMS
python3 -IB analyze.py
python3 -IB test_plan.py
~~~

The operator supplies a privately owned directory with `public`, `private`, `logs` and `runs` subdirectories. Place these public files in `public`. Use the separately source-qualified SDK, the complete offline registry and the two real Git states in `plan.json`. The host adapter sets up a fresh Linux mount namespace for each chronological installation. At the same physical and logical locations for every arm, it provides an ordinary source/registry tmpfs and a separate target/build tmpfs, the physically fixed SDK, authenticated rustup proxies, and read-only native references. It runs the worker as an ordinary user without capabilities, with `no_new_privs` set. It also enforces the capacity floors and host nonoverlap externally. A general command on a stock toolchain would be a different experiment.

The source input directory contains a Git pack with both commits, a `sources.json` recording `role_A`, `role_B`, `trees`, `lockfile` and `pack_sha256`, and `historical-index.json` with 505 versions and a 465-row list of `name` and `sha256`. A read-only donor supplies `cargo-home/registry`. The canonical directory contains an empty `products` and `shared` on its private 10 GiB output tmpfs and a fixed `sdk`. Both `products` and `shared` are genuine subdirectories of `.allocation`. The immutable external consumer source must have its original compiled source path and match `consumer.rs` byte for byte. Retain the actual role-specific `out_dir` from the Cargo messages. A newly copied compiler can change Cargo's namespace and the ELF debug paths even with equal compiler bytes.

The native qualification supplies independent full CLI and reader ELF bodies for A and B with both options, physical tool and output identities, complete Cargo messages, and real compiler and stock linker argv. If either same-branch complete CLI differs across options, `compare_current.py` can verify the genuine current pair using the source-matched, checksum-pinned LLVM DWARF decoder. It reads the exact path Cargo reported for jemalloc, verifies the stock link really received it, checks the entire two output files outside the allowed ranges and compares the complete decoded info and macro streams. Only the option-specific jemalloc unit directory may differ inside the otherwise identical native build path. The file name in the first DWARF-dumper display line is presentation data. A prior proof is eligible only for the identical complete file pair. Within each option there is no byte normalization.

~~~sh
python3 -IB public/compare_current.py "$NATIVE" "$STUDY/current-elf.json" \
    --decoder "$DWARFDUMP" --capacity-disk "$INPUT_DRIVE" --capacity-disk "$RECEIPT_DRIVE"
python3 -IB public/prepare_reference.py "$NATIVE" "$PREVIOUS_VERIFIED_ELF_PROOF" \
    "$STUDY/native-reference.json" --current-elf-proof "$STUDY/current-elf.json"
~~~

The host's private configuration supplies `receipts`, `canonical`, `source_inputs`, `donor`, `proxies`, `native_custody`, `consumer` and four assigned `cpus`. The private control records the source and receipt mounts, the four independent physical native studies, the two previously completed parser studies, the fixed 57-file SDK inventory, the immutable route and the pre-Cargo per-slot front gate. Inside each ready namespace it invokes:

~~~sh
python3 -IB "$STUDY/public/run_slot.py" "$STUDY/private/config.json" "$SLOT"
~~~

The compiler starts from the two real Git branches on every fresh installation. Only the incoming option differs. The worker generates complete Cargo streams, CLI and linked-reader outputs, raw source/roster checks, timing and a settled allocation ledger on all five visits. A terminal audit reopens those actual records. Enter confirmation only if the terminal pilot was independently verified and all four return ratios exceeded two. To recompute phase and whole-study effects with the small public projections, run:

~~~sh
python3 -IB analyze.py --stage pilot pilot.json
python3 -IB analyze.py --stage confirmation confirmation.json
~~~

For the complete private data layout, `collect.py "$STUDY" --stage pilot` or `--stage confirmation` first checks every retained Cargo exit, actual standard output and error, typed roster and dirty set, external verdict, native full files, mount identities and paired receipts. It then emits the corresponding portable `observations.json`, analysis and checksum. Use a fresh output directory for any reviewer replay. The original data and all failed admissions remain available unchanged.

Before enrolling Cargo, run `python3 -IB test_timer.py WORKING_TMPFS RECEIPT_DIRECTORY` on two distinct devices with at least one free MiB apiece. It checks six ordinary child processes with known sleep intervals and a real CPU-consuming grandchild. It verifies both output streams, blocking exit and descendant CPU accounting. These probes supply no timing samples.

