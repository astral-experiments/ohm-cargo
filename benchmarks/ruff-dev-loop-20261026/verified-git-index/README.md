# Git index verification in Ruff’s development loop

The final Cargo head is `b5330b2788eb7ded3d0f7de4469110fb8529f014`. Its parent `646d5da91f94fa09ba451d70564190d54d2183d8` introduced the gated optimization. The follow-up moved `src/sources/path.rs` to `src/sources/path/mod.rs` byte-for-byte to satisfy Cargo’s module-layout lint. It changes the Ohm release-14 Cargo at `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. Each arm used the same Ruff checkout revision `93526150df078af7dd8fc4226cdcc469539d2001`, release compiler, link path, Cargo release profile, Ohm-defaults feature and release PGO data. The source edit replayed [Ruff’s ty_vendored include path correction](https://github.com/astral-sh/ruff/commit/66991ac20c23ab98d358fae54d35956451245885). The edited checkout is restored at the end of each cohort. Binary, patch and training-profile digests are in [sha256.txt](sha256.txt). The underlying release-PGO build setup is described in [component-pgo](../component-pgo/).

## Final PR head

The paired reduction is `100 × (1 − candidate / parent)`. A negative number is a cost. Callgrind 3.22 traced the whole command including subprocesses. Each warm sample required Cargo to be the only process. Preflight and finishing checks verified the identical fresh artifact roster. The edited samples required the same 182 targets, one dirty ty_vendored library, a matching complete pre-edit target, and one process each for Cargo, rustc and the build script. We also required the SHA-256 of the Git index before and after every command to match its starting value.

| Shipping comparison | Parent median instructions | PR median instructions | Paired reduction | 95% median interval | Favorable pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full check, 520 fresh units | 920,426,778 | 862,807,290 | +6.263% | +6.258 to +6.268% | 12/12 |
| Historical ty_vendored library edit, 181 fresh and one dirty | 754,814,194 | 700,583,226 | +7.210% | +7.160 to +7.233% | 12/12 |

The full check and edited check are the two primary comparisons. Each cohort shuffled six parent-first and six candidate-first assignments before measurement. The two-sided exact randomization test enumerates all 924 balanced assignments. The positive median and interval gates and Holm-adjusted p < 0.05 apply across the full and edited primaries. The median interval uses the third and tenth ordered paired reductions. [pairs.csv](pairs.csv) preserves every scored pair, the order, the seed, fresh and dirty unit counts, and the child instruction totals. [summary.csv](summary.csv) also records each observed range and raw p-value.

| Real-edit comparison | Parent Cargo | Candidate Cargo | Parent rustc | Candidate rustc | Parent build script | Candidate build script |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Selected algorithm | 457,324,221 | 403,130,450 | 149,698,961 | 149,653,366 | 146,762,508 | 146,753,254 |
| Gated code, before module rename | 458,214,774 | 403,791,494 | 149,740,430 | 149,655,266 | 146,833,098 | 146,804,843 |
| Final head | 458,210,846 | 403,839,922 | 149,890,118 | 149,960,118 | 146,809,877 | 146,809,618 |

The final-layout ELF retained exactly 25,340,746 bytes of machine code, with 58,806 bytes differing at the same offsets. For that reason the final head uses its own independent comparisons. [Loaded section digests and byte differences](layout-elf.csv)

## Gated code before the module rename

The following cohorts used the separate binary built from the immediate parent at `646d5da91f`. Each primary improved in 12/12 pairs with raw p = 0.00216 and Holm-adjusted p = 0.00433.

| Comparison | Parent median instructions | Candidate median instructions | Paired reduction | 95% median interval | Favorable pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full check, 520 fresh units | 920,437,127 | 862,737,901 | +6.268% | +6.253 to +6.275% | 12/12 |
| Historical ty_vendored library edit, 181 fresh and one dirty | 754,800,898 | 700,195,120 | +7.228% | +7.187 to +7.245% | 12/12 |
| Warm ty_vendored check, 182 fresh | 416,925,723 | 362,521,428 | +13.048% | +13.037 to +13.068% | 12/12 |
| Full build, 501 fresh | 1,504,064,990 | 1,446,277,762 | +3.841% | +3.827 to +3.851% | 12/12 |
| Full check with a new proof on every run | 920,560,240 | 921,423,232 | -0.102% | -0.125 to -0.067% | 0/12 |

## Selection and cold cost

The simpler alternative reads, hashes and decodes the live index at both calls in package discovery and listing. The selected version uses Gitoxide’s own snapshot primitive to share the first decode across those calls. We fixed a threshold of at least 80% retained savings to select the double-read version. A separate, previously unmeasured Ruff checkout and private toolchain ran the release, selected and double-read subjects in each of 12 blocks. All six arm orders appeared twice. The selected algorithm reduced full-check instructions by 6.270% (95% interval 6.258–6.275%). Double-read reduced them by 4.888% (4.863–4.891%). Double-read retained 77.908% of the gain (77.824–78.038%). The series and its position-conditioned exact tests are in [three-arm.csv](three-arm.csv) and [decision.json](decision.json).

Each true-cold pair starts by evicting the already verified fixture-specific record before **both** arms. The release leaves the private record absent. The selected arm must mint the identical 32-byte record by verification. All true-cold comparisons check the same full 520-unit graph and exact live index. The selected-algorithm measurements below preceded the explicit Ohm opt-out guard. [selected.patch](selected.patch), [double-read.patch](double-read.patch) and [shipping.patch](shipping.patch) and [shipping-layout.patch](shipping-layout.patch) distinguish the production diffs. The final commit also adds a focused regression test.

| Before the opt-out guard | Parent median instructions | Candidate median instructions | Paired reduction | 95% median interval | Favorable pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full check | 921,233,520 | 863,472,828 | +6.270% | +6.254 to +6.289% | 12/12 |
| Historical library edit | 753,813,440 | 699,547,074 | +7.195% | +7.129 to +7.242% | 12/12 |
| Warm scoped check including one observed cold miss | 416,634,740 | 362,246,018 | +13.053% | +13.012 to +13.078% | 11/12 |
| Independent byte-pinned warm scoped check | 416,449,167 | 362,091,968 | +13.046% | +13.035 to +13.064% | 12/12 |
| Full build | 1,503,586,756 | 1,445,724,836 | +3.844% | +3.835 to +3.859% | 12/12 |
| Full test compilation | 1,115,975,200 | 1,057,792,450 | +5.212% | +5.203 to +5.214% | 12/12 |
| Full check with a new proof on every run | 919,931,836 | 920,958,909 | -0.111% | -0.123 to -0.104% | 0/12 |
| Double-read alternative on a separate checkout | 921,067,596 | 875,955,722 | +4.897% | +4.888 to +4.910% | 12/12 |

The original supplementary scoped series includes a true cold candidate after an independent Git status refreshed that checkout’s index. That observation cost 1.093% and remains in the raw data. Its trace ran a full index verification and minted a new private record. A separately scheduled repetition pinned the index bytes and improved all 12 pairs. An earlier attempt to restore a pilot target next to a different pre-edit source timestamp failed preflight before scoring. The measured edit cohorts made new complete verified checkpoints. The first experimental prototype conservatively fell back for the real host’s `index.threads=true`. Its mechanical checks contributed no scored pairs.

## Profile and correctness

On the 1,708,084-byte, 11,244-entry Ruff index, a representative release check spent 57,061,965 instructions in Gitoxide’s index-checksum call. The selected helper’s inclusive initiating-thread cost was 7,101,481 instructions, including 4,292,250 for BLAKE3, 2,435,474 for index decoding and 357,028 for lazy domain setup. These nested call-edge counts describe one observed profile. The whole-command comparisons include worker threads and remaining Cargo work. [profile-edges.csv](profile-edges.csv)

An eligible first encounter checks the nonzero stored SHA-1 trailer with Gitoxide’s collision-detecting implementation and decodes the same bounded buffer. Only a successfully decoded standalone index produces a record. Subsequent commands read every byte afresh from one file descriptor, including the trailer, and accept a full 256-bit content match from an owner-private regular record. The digest domain includes Cargo.lock. The 4,096 private slots bound the number of persistent records. Cargo still decodes current entries, runs its ordinary directory walk, and enumerates live untracked files.

This uses the same trusted Unix Cargo-home ancestry requirement as Ohm’s registry-manifest cache. Code running as the Cargo-home owner is inside that trust boundary. Reduced-trust repositories, unsupported or explicitly constrained Git settings, split indexes, unsigned indexes, and files outside 256 KiB to 8 MiB use Gitoxide’s regular path. The explicit `-Zohm-defaults=no` bypass runs before any index or certificate lookup. The subprocess matrix compares the parent and candidate’s package file lists and exit codes. It covers backdated body/trailer changes, corrupt receipt values, world-accessible files, private-directory permissions, symlinks, FIFOs, thread/skipHash/allocLimit settings, a real split index, its damaged shared base, and all four SHA-1 collision fixtures. The short SHA-mbles inputs are padded to the eligible size before constructing their regular SHA-1 trailers. [Portable correctness script](semantics.py) and [observations on the gated code](correctness.txt) and [the final head](correctness-final.txt).

## Reproduction

On x86-64 Linux use Valgrind, taskset, rsync, Git and Python 3, a disposable Ruff worktree at the pinned commit, the release Ohm compiler distribution, and Cargo binaries built from both revisions using the release PGO profile in [sha256.txt](sha256.txt). `CARGO_HOME` must be a private directory under trusted ancestry with Ruff’s locked dependencies prefetched. Point `RUFF_TARGET` at an exclusive target for this checkout and `SHARED_BUILD_DIR` at a separate shared directory. `edited.py` restores the complete target before every arm. Reserve space for a second copy of that target. The private runner assigns both Cargo arms a single executable path. It copies compiler files independently when preparing a new state.

```sh
export GIT_OPTIONAL_LOCKS=0
export PYTHONPATH="$BENCHMARK_DIR"
common=(--parent "$PARENT_CARGO" --candidate "$CANDIDATE_CARGO" \
        --toolchain "$OHM_RELEASE" --ruff "$RUFF_CHECKOUT" \
        --target "$RUFF_TARGET" --shared "$SHARED_BUILD_DIR" \
        --state "$PRIVATE_RUNNER" --pairs 12 --cpu "$CPU")

python3 "$BENCHMARK_DIR/fresh.py" "${common[@]}" \
    --output "$RUNS/check" --design paired --jobs 4 --mode check --seed 628209
python3 "$BENCHMARK_DIR/edited.py" "${common[@]}" \
    --output "$RUNS/edited" --seed 496863
```

For the other shipping workloads, use `--mode build --jobs 6 --seed 538591`, `--mode test --jobs 6 --seed 819229`, or `--mode check --package ty_vendored --jobs 4 --seed 386067`. The test mode passes `--no-run`. For cold measurements, use a dedicated Cargo home with one verified record and `--mode check --cold --jobs 4 --seed 652819`. Set a distinct output directory each time. The correctness fixture creates a fresh repository and private Cargo home under its output directory.

```sh
python3 "$BENCHMARK_DIR/semantics.py" \
    --parent "$PARENT_CARGO" --candidate "$CANDIDATE_CARGO" \
    --toolchain "$OHM_RELEASE" --output "$RUNS/correctness" --cpu "$CPU" \
    --collision-dir "$SHA1_CHECKED_0_10_0/tests/data"
```
