# Storage for switch-only incremental retention on the complete Ruff CLI

After the final unchanged B build, the complete Cargo target and build directories occupied 2,305.9 MiB with the option off and 2,570.7 MiB with it on. The difference was +264.9 MiB (+11.49%). The largest allocation observed across the entire history was 2,837.2 MiB off and 3,123.5 MiB on, a difference of +286.4 MiB (+10.09%). This study measured storage in one independent installation of each option. It provides no wall-time or instruction estimate.

Both arms used the same physical source-built Rust compiler at `08d49cba6aacb0cac27a96eea335ed1c7439f483`, the same source-built Cargo at `2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c`, and the signed distribution’s stock Wild binary. The compiler selected a second incremental session only with `-Zohm-branch-cache=yes`. With retention enabled, packing was eligible when the most recently finalized eligible session belonged to the other checkout.

### Target and build storage

| Cargo phase | Complete off MiB | Complete on MiB | Delta MiB | Incremental off / on MiB | Observed peak off / on MiB |
|---|---:|---:|---:|---:|---:|
| empty-A | 2,304.5 | 2,304.5 | +0.0 | 1,037.4 / 1,037.4 | 2,304.5 / 2,304.5 |
| first-B | 2,411.3 | 2,906.8 | +495.6 | 1,144.6 / 1,640.2 | 2,690.5 / 3,123.5 |
| return-A | 2,514.0 | 2,563.5 | +49.4 | 1,246.9 / 1,296.4 | 2,837.2 / 3,108.7 |
| return-B | 2,305.9 | 2,570.7 | +264.9 | 1,039.2 / 1,304.0 | 2,673.4 / 3,123.5 |
| unchanged-B | 2,305.9 | 2,570.7 | +264.9 | 1,039.2 / 1,304.0 | 2,305.9 / 2,570.7 |

The first visit to B added +495.6 MiB (+20.55%). After returning to A the difference was +49.4 MiB (+1.97%). After returning to B it was +264.9 MiB (+11.49%). The independent, empty B controls occupied 2,304.3 MiB off and 2,304.3 MiB on.

### What occupies the additional disk space

On the final B, the allocated change in the two raw and packed tables together was +49.6 MiB. All other inode classes together accounted for +215.3 MiB.

| Physical file class at final B | Off MiB | On MiB | Delta MiB |
|---|---:|---:|---:|
| packed-query-and-dep-tables | 0.0 | 750.6 | +750.6 |
| raw-query-and-dep-tables | 771.7 | 70.7 | -701.0 |
| native-object | 340.0 | 514.2 | +174.2 |
| rust-metadata | 243.1 | 279.3 | +36.2 |
| other-regular | 23.6 | 28.2 | +4.7 |
| incremental-work-product-index | 0.3 | 0.5 | +0.2 |
| rust-link-recipe | 0.1 | 0.1 | +0.0 |
| cargo-dep-info-or-fingerprint | 6.2 | 6.2 | +0.0 |
| directory | 0.0 | 0.0 | +0.0 |
| executable | 170.5 | 170.5 | +0.0 |
| native-library-archive | 162.1 | 162.1 | +0.0 |
| rust-library-archive | 472.7 | 472.7 | +0.0 |
| shared-library | 115.5 | 115.5 | +0.0 |

The table charges each device/inode pair once across target and build. A plus-separated class has names with more than one classification and stays in its own row. Incremental totals include every inode with an incremental path. `storage.json` also gives the incremental-only, cross-boundary and cross-root totals, and the raw/packed and residual changes at each visit. On the host, file classification opened the complete set of regular files to inspect their type and read ELF program headers where appropriate. The offline pass reclassifies each name from its observed file type and checks every hard link and byte charge against the independent raw namespace commitment. Archive members remain charged to their complete archive. Per-inode lists and unknown or unseen link counts are available for every settled phase.

### Measurements and native controls

The 10 GiB output tmpfs held only target and build on the same device, preserving cross-directory hard links. Source, Git, Cargo home and temporary files were on a separate 6 GiB tmpfs. The read-only toolchain was external to both. All 57 SDK roles had identical physical device/inode, size, modification and change times and SHA-256 across the four installations. The allocation sampler took 190,617 samples. It measured `fstatvfs` before starting Cargo, nominally every 10 ms while the observed Cargo process ran, and just after it exited. Per-command median gaps ranged from 10.135 to 10.147 ms. The largest gap was 419.271 ms. A brief spike between samples can exceed the reported maximum. At each boundary, two separate complete namespace scans agreed with the observed superblock allocation for that tenant. A separate pair of scans verified inode aliases and classified files after Cargo had exited.

Ruff A is `b5dba861cc38e3f7fb4524c9ceba3e01a474ea13` and B is `7b13f01ba1569887a25670820764b24c206da8e5`. The historical #28335 edit changed 169 paths. Both workloads used 505 locked registry archives and 465 verified sparse-index records. `cargo +ohm build -p ruff --bin ruff --locked --offline -j4 --message-format=json` produced 375 typed artifacts on every visit. Cold visits recorded 379 SDK rustc invocations, 69 actual stock Wild links and 37 build scripts. Each source switch performed 20 rustcs, one Wild link and one build script. The final unchanged commands invoked zero rustcs and zero linkers.

The genuine Ruff CLI validated its version, source revision, a clean input, an E711 diagnostic, the exact corrected bytes from an unsafe fix, the clean recheck, and invalid syntax. An independent Rust consumer linked the actual parser/AST libraries, accepted valid input and rejected invalid input. Its native `Expr` size was 64 bytes for A and 56 for B. Each warm result reproduced its same-option independently empty CLI and reader byte for byte. The absolute paths, Rustup proxy, SDK, source and target/build names were fixed across installations.

| Branch / option | Complete CLI SHA-256 | Independently linked reader SHA-256 |
|---|---|---|
| off-A | `0d33178310994503675cb55d2a35a395dfdf71d1c078d970be8056ec494215d3` | `87dedef6a2b66c1998dd3bc4dcca0b45dd9713fbb28985bd45a8985f58798816` |
| on-A | `8218f509bf9d1b2c7228a5ffdc5f783fe45742e14e19e39f427c8f87e7d67758` | `87dedef6a2b66c1998dd3bc4dcca0b45dd9713fbb28985bd45a8985f58798816` |
| off-B | `2a49674cf5d71b4f9145314bbf3fff1fd11e4179134596d4aff841245ef031d4` | `d5cdbc87717ddd119f74c4b840dd9fa2efc7cbc0af02ec5707a96ae738c839f0` |
| on-B | `61eee1f72058a4bc01a6570b778a97bf2ff3f3e7a857f772739c3f8caa1bf697` | `d5cdbc87717ddd119f74c4b840dd9fa2efc7cbc0af02ec5707a96ae738c839f0` |

The current raw full CLI bytes differ from at least one earlier 8ea build. Its DWARF and provider audit does not qualify that changed file. The current report retains all raw native comparisons and the independent within-option clean evidence.

### Verify locally

Run these commands in the evidence directory with Python 3.11 or newer. They re-read every raw sampler and inode stream, independently reconstruct the name/physical/inode/class commitments, recheck the complete checksums and native counts, then exercise deliberately broken cases.

```sh
sha256sum -c SHA256SUMS
python3 -IB audit.py
python3 -IB metrics.py
python3 -IB mutations.py
```

For a new local measurement, `python3 -IB measure.py --help` gives a single-build entry point for a compatible Ohm SDK, an already checked-out Ruff source and an exclusive Linux tmpfs containing ordinary-user-owned `products` and `shared` directories. Call the command once per checkout at fixed paths. `cli-controls.py --help` exercises the seven CLI verdicts on a built executable. The archived study also checked actual execs and executed `consumer.rs` against the resulting libraries. The supplied single-build entry point does not perform all those checks automatically.

### Separate read-only HOME admission

The original 145 GiB HOME entry condition first observed 155,580,874,752 bytes. At the handoff it still had 155,580,801,024 bytes. That controller launched zero Cargo processes and zero rustcs. Its process identity and childless state were verified and its exit was observed with a pidfd before the separately registered route could start. The actual read-only HOME backing remained above 140 GiB throughout each alternative installation. A verifier outside the private mount namespace captured the physical devices, inodes and authentic input hashes. Immediately before Cargo and after every installation the unprivileged worker verified those devices and every visible alias read-only, including matching its physical HOME and scratch identities to the outside observer. This cohort had zero writable HOME budget. The 384 MiB scratch receipt cap, both independent tmpfs, genuine system memory and other reserve checks are recorded for all four cases. The alternate enrollment SHA-256 is `54ffb9a2433e909fff8913c8e0624d81d50cd89a5e26b548945e9aab62a04091`.

### Repeat the source history on another Linux installation

Install the source-built 08d49 Ohm compiler and matching Cargo/Wild under the local Rustup alias `ohm`. Set `CARGO_HOME` to a private cache populated for the two locked Ruff revisions, including jemalloc build dependencies. Supply a local Ruff Git clone containing both commits. A different compiler, absolute checkout path or system library environment can yield different physical sizes and native hashes. The reviewer script records its actual tool digests and, with `--product`, checks all 55 source-product members. This standalone frontend was syntax-checked and its public CLI was exercised. The complete reported 12 Cargo commands were acquired with the separately registered privileged controller, including its per-thread exec and read-only mount checks.

Run the following from the packet directory with a new working directory and an empty, dedicated mountpoint you own. The loop creates a separate anonymous filesystem for each off/on and independently empty control. Keep the working and mount paths the same for all four installations. An executable-compatible Linux filesystem, GNU findmnt and a preconfigured Rust/C toolchain are required. The original host used 10 GiB for the output tmpfs and supplied its own fully locked registry. A local source clone and the smaller receipts are outside that output filesystem.

```sh
set -eu
: "${RUFF_GIT:?Set this to your local Ruff clone}"
: "${STUDY:?Set this to a new owned absolute directory}"
: "${CARGO_HOME:?Set this to an already populated private cache}"
mkdir -m 700 "$STUDY" "$STUDY/mount"
for role in off-storage on-storage off-clean-B on-clean-B; do
  sudo mount -t tmpfs -o "size=10G,mode=0700,uid=$(id -u),gid=$(id -g)" tmpfs "$STUDY/mount"
  mkdir -m 700 "$STUDY/mount/products" "$STUDY/mount/shared"
  python3 -IB replay.py --git-source "$RUFF_GIT" --work "$STUDY/work" --output-tmpfs "$STUDY/mount" --case "$role"
  sudo umount "$STUDY/mount"
done
```

The script builds and runs the complete ELF and independent reader for every checkout, captures the sampler and double inode census, checks the 375 typed results, records each case’s actual stdout/stderr and per-inode classes, and compares same-option clean B with its returns. It leaves the original source clone untouched. For native parity, keep `CARGO_TARGET_DIR`, `CARGO_BUILD_BUILD_DIR`, compiler options and tool paths consistent; the script sets the output paths and the single opt-in flag. Independently built source images can be supplied with `--product /path/to/product.json`.
