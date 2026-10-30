# A separate receipt filesystem for the full Ruff CLI branch-return study

This pre-observation registration adds one way to retain the raw evidence. It keeps the same host, four CPUs, compiler, Ruff checkouts, ordinary Cargo command, sample order and statistical decision. The original registration still has first choice. Both registrations had zero full-CLI time samples when this alternative was prepared. [Original registration](https://github.com/astral-experiments/ohm-cargo/tree/e91f82ceeeb9bc377dd0efbc66d3f509552d66a2/benchmarks/ruff-dev-loop-20261030/branch-switch-incremental/storage/alternatives/switch-only/full-cli-timing/registration)

## Choose exactly once

Two earlier twelve-pair parser confirmations have exclusive use of the host. The selector requires the successful terminal and independent verification of each run and their matching source, workflow and pair count. It also requires an independent quiet-host release and a complete readback of both public registrations. The existing 12-command native qualification and current-image ELF/DWARF receipts are hash-bound.

At the first eligible selection it tries these routes in order.

1. Use the original collector if scratch has more than 140 GiB plus 384 MiB, HOME has more than 140 GiB and OS available memory exceeds 75 GiB. The published original controller prefers its 145-GiB HOME mode when it qualifies. It owns its own release marker.
2. Otherwise consider the external collector only if scratch has more than 140 GiB plus 8 MiB, HOME has more than 140 GiB plus 384 MiB, and available memory exceeds 75 GiB. Both physical volume identities must match the original host. Validate the original waiter's PID, complete argv, process start tick, all thread child lists, absent release/route markers and empty run/log directories. Stop only this process through a retained kernel pidfd. Reopen its stopped state and recheck both routes before committing one choice with no-clobber publication and directory fsync.
3. If neither route qualifies, leave the original enrollment waiting. A choice stays fixed through qualification, pilot and any confirmation. A pending or failed slot cannot be replaced by the other route. A second explicit release, bound to the selected record and published alternative, enables external native work.

## What the different route writes

Every incoming real HOME and scratch filesystem alias is read-only in the measured mount namespace, including aliases outside the checkout path. The physical receiver is a separate, fully preallocated 383-MiB ext4 image on the HOME volume. Its dedicated directory and all other physical files together must use less than 384 MiB. The launcher checks complete image bytes and actual allocated blocks after formatting. A reserved 180-MiB file inside the image protects failure capture. The budget applies even when the receiver filesystem is nearly full.

The receiver mount is absent from every native process. The measured user has UID 1000, zero effective capabilities and no-new-privileges. It cannot write any observed alias of the durable HOME or scratch devices, or an accessible block-device node for the external receiver. A third 384-MiB tmpfs receives raw streams **after** the unchanged timer has returned. Eight MiB of that spool is preallocated exclusively for recording a failure. Each installation requires more than 16 MiB of remaining spool headroom before it starts. The study's charged scratch writes are zero.

The original source/registry tmpfs remains 6 GiB. A separate 10-GiB tmpfs holds the two whole-Cargo target/build trees. All original visible paths and the 57 actual SDK file identities are rechecked at entry. The original timer still passes empty, seekable anonymous regular files on the source filesystem to Cargo. It reads the monotonic clock immediately after the same blocking `wait4`, records descendant CPU and only then copies stdout and stderr. The external collector does no receipt compression or native hashing during a timed child. Both filesystems must remain above 140 GiB, OS memory above 52 GiB, free source above 1 GiB and free build space above 2 GiB. Each new installation again requires the **full** entry margins on top of the free bytes after allocating the image.

The producer performs the same complete byte comparisons for each CLI and independently linked reader. A successful native body already exists in the immutable, independent empty reference, with full content verified. After the last native process exits the holder opens the genuine current CLI and reader by their original names and transmits read-only FDs over an ordinary Unix socket. The collector verifies kernel peer credentials, ancestry, namespace, identities and complete contents. Failure captures preserve the actual emitted files and diagnostics, including a wrong executable. A missing result is recorded as absent. Source and native mounts stay alive through fsync and a separate full compressed and per-member readback. Only then can the authenticated receiver acknowledge the slot. An interrupted transfer keeps the producer and its descriptors. A full, failed or inconsistent receipt stops enrollment, retaining the partial evidence and whatever native output the genuine attempt produced.

## The five visits and the decision

The external route first runs one newly installed unscored history per option, in on/off order. It checks all five visits, rosters and complete own-option bodies against the already closed independent controls. Its receipt tree is disjoint from the score tree. No qualification elapsed observation goes into the estimator or a resource decision.

Each timed fresh installation uses `cargo +ohm build -p ruff --bin ruff --locked --offline -j4 --message-format=json` on both genuine Ruff Git branches. Retention off leaves encoded Rust flags absent. Retention on supplies exactly `-Zohm-branch-cache=yes`. Each history builds empty A, first B, return A, return B and unchanged B. Full native bodies, seven CLI outcomes and the linked AST reader must match their same-option references. All storage increases, both CPU components, Git costs, cold and initial feature costs and both return directions are reported.

The pilot has two new mirrored pairs. All four return ratios must exceed 2 before confirmation. The subsequent twelve new pairs use the original three balanced four-pair blocks and frozen order. Report median off/on ratios, order and every tie. Each simultaneous lower and upper interval uses ranks 3 and 11 of 12. The asymmetric one-sided tail probabilities are 79/4096 and 13/4096. Bonferroni family coverage for both directions is at least 95.5078125%. Both lower endpoints must exceed 2 for the declared workflow result. Report the randomization calculation over all 216 permitted schedules. The original `measure.py`, `run_slot.py`, `collect.py`, `analyze.py`, schedule, census, consumer and native oracle bytes are used. Earlier 6b7 raw-cache timings, parser timings and receiver calibration provide zero scores.

## Reopen or repeat the calibration

`calibration.json` contains a source-linked, independently reopened, zero-sample Linux calibration. The receiver's small ext4 image was backed by bounded RAM on the coordinator. Separate real block-backed ext4 fsync and readback also passed. The coordinator did not meet the production host thresholds. The original failed isolated import and partially allocated formatted image are preserved as acquisition records. `verify.py --qa` independently reopens the original Rust and C native bodies, raw messages, distinct negative and every nested receipt.

For a repeat, provide an independently authenticated existing Ohm SDK and its rustup proxies, the pinned original registration directory, an owned scratch directory on a second filesystem, and a new empty result directory owned by UID 1000. Use Linux with passwordless privilege for private mounts and the listed GNU tools. The small test compiles a local fixture and needs no downloads or registered Ruff jobs.

```sh
install -d -m700 "$NEW_RESULTS"
source_ns=$(readlink /proc/self/ns/mnt)
sudo -n env ORIGINAL_MOUNT_NS="$source_ns" unshare -m --propagation private \
  bash ./run_qa.sh "$NEW_RESULTS" "$ORIGINAL_REGISTRATION" "$SDK" "$PROXIES" \
    "$REAL_HOME" "$SECOND_MOUNT" "$OWNED_DIRECTORY_ON_SECOND_MOUNT"
printf '%s\n' "$?" > "$NEW_RESULTS/exit"
python3 -IB ./verify.py --qa "$NEW_RESULTS"
```

The public `deployment` files are the exact host adapter source. An enrolled site supplies its private four-path layout, the read-only original deployment manifest and two distinct, independently authenticated release records. The private source adapter derives its carrier from the original manifest and compares the unmodified parts byte for byte. The original data stays in place. After a terminal stage, mount the closed receiver image read-only and run the following independent whole-archive check.

```sh
python3 -IB ./verify.py --store "$RECEIVER_STORE" --stage pilot --original "$ORIGINAL_REGISTRATION"
```

Use `--stage confirmation` for a completed twelve-pair study. A partial, failed or unexpected archive roster cannot certify a completed stage.
