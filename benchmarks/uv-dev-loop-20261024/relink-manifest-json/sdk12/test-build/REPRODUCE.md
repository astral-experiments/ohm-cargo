# Reproducing the Cargo test-build measurement

Run `python3 -I -B reproduce.py` from the evidence directory to check the 32 published profiles. It authenticates the compressed and decompressed bytes, reconciles every disjoint self-cost with the final total and the original stderr counter, then recomputes both paired results. File and object path definitions have injective SHA-256 labels. The command retains its arguments and uses the public name `cargo` for the common executable path. The original private collector checked full stderr, compiler traces, outputs, freshness and restoration.

## Build the two Cargo binaries

Use Linux x86-64, stock Rust 1.99.0 at `b940084d7`, GNU binutils and a new detached checkout at the SDK12 Cargo commit in `source-and-recipe.json`. Seed its locked registry index and crate archives into `$BUILD_ROOT/cargo-home`. From that checkout, run `STOCK_BIN=/absolute/stock/bin BUILD_ROOT=/absolute/build bash /absolute/evidence/build-cargo.sh`. The same physical source, target and package-home directories are used for both builds. The script checks both Git trees and embeds the common commit in both binaries. It builds with optimization level 3, ThinLTO, one codegen unit, debug information level 1, static dependency features and disabled incremental compilation. It retains the linked binaries before stripping debug sections. [Ohm Cargo source](https://github.com/astral-sh/ohm-cargo/commit/fdd26156be98618e2e01a9e02703edac71b79a35).

Run the focused `relink_cache_tests` module and the four relink/native-archive tests listed in `source-and-recipe.json`. Check the full and stripped binaries' 31 allocated ELF sections, dynamic libraries and verbose Cargo versions. The recorded binary hashes identify the measured builds. A new machine should record its own toolchain, libraries, flags, source trees and binary hashes.

## Prepare the profiler

Use Ubuntu Valgrind `1:3.22.0-0ubuntu3`, its matching debug package and matching libc debug files. Verify the source and patch digests from `source-and-recipe.json`. Extract the source package with `dpkg-source -x`. In the extracted tree, build the distribution source and the expanded version at the same absolute path.

```sh
./configure --enable-only64bit --prefix=/usr --libexecdir=/usr/libexec
make -j8 include/vgversion.h default.supp valgrind.pc
for sub in include VEX coregrind callgrind; do make -j8 -C "$sub"; done
cp callgrind/callgrind-amd64-linux "$build_root/stock-callgrind"
patch -p1 -i "$evidence_root/profiler/large-brk.patch"
make -j8 -C coregrind
make -j8 -C callgrind
cp callgrind/callgrind-amd64-linux "$build_root/expanded-callgrind"
```

Use three private copies of the same runtime for qualification. Leave one packaged, replace the Callgrind executable with the stock source build in the second, and replace it with the expanded build in the third. Every other runtime file and alias must match. The patch increases only Valgrind's simulated Linux data-segment limit from 8 to 512 MiB. Run the loop and heap controls in `profiler/` against all three runtimes. The assembler settings are `ITERATIONS=17011`, `ITERATIONS=17029`, `REQUEST_BYTES=67108864` and `REQUEST_BYTES=537919488`. Compile each with `as --64 --defsym NAME=VALUE -o case.o SOURCE.S` and link with `ld -static --build-id=none -e _start -o case case.o`. The loops must produce 51,035 and 51,089 instructions. The 64 MiB probe succeeds only under the expanded core and natively. The 513 MiB probe succeeds natively and must exit 77 with a brk warning under all three profiler runtimes. Each loop must exit zero everywhere. Reject any brk-overflow warning in a real Cargo sample.

## Run the test-build workload

The pinned uv checkout is `3d82a6ad5a7eab8c68236553b7846517767c4b61`. Install the published Linux SDK12 rustc, rustdoc, sysroot, Cargo and Wild in a private directory and verify the bundle SHA-256. The published Rust compiler and Wild stay fixed across Cargo arms. Create a common executable slot at `$study_root/bin/cargo` and independent per-arm directories for target outputs, shared build files and package state. Move the selected directories into the same physical active paths each time. Seed only locked registry archives and indexes. Warm each arm separately with `cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8` and require zero rustc and rustdoc calls on the next command. [uv revision](https://github.com/astral-sh/uv/commit/3d82a6ad5a7eab8c68236553b7846517767c4b61) · [Ohm SDK12 release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-12).

Use explicit common `RUSTC` and `RUSTDOC`, `CARGO_BUILD_JOBS=8`, `CARGO_TERM_COLOR=never`, `CARGO_TARGET_DIR=$study_root/target`, `CARGO_BUILD_BUILD_DIR=$study_root/shared`, `CARGO_HOME=$study_root/package-home` and `PATH=$study_root/bin:$study_root/runtime/bin:/usr/bin:/bin`. Leave `CARGO_INCREMENTAL`, `LD_LIBRARY_PATH` and `LD_PRELOAD` unset in the native environment. Set `OHM_BENCH_NORMALIZE_VALGRIND_ENV=1` and the private expanded `VALGRIND_LIB` in both arms. Build the supplied adapter with the matching Valgrind headers and `cc -shared -fPIC -O2`. Use a fresh private `TMPDIR`, the same home directory for both arms, and record all applicable Cargo configuration files.

The fixture appends an equal-length comment to the ordinary uv library source and changes the five bytes in `before` to `after_`. The original source bytes and mode are restored after each sample. `one-profile.sh` contains one complete before/after invocation with the exact strace and Callgrind flags. Set its `study_root`, `evidence_root`, `profiling_root`, `tracer`, `selected_cargo`, `sample_root`, `block_root` and `pair_index` to fresh absolute paths or the pair index as appropriate. Activate the selected arm's parked bank. Run `taskset -c 8 bash one-profile.sh`. The fixture's `--variant baseline` selects the shared physical target slot for either Cargo executable.

Admit both arms on each machine using one excluded native build and one excluded profile. Compare the full compiler argument and environment multiset, preserving multiplicity and the order of every individual argument. The sole environmental omission is the expired `CARGO_MAKEFLAGS` file descriptor string. Expect two ordinary uv compiler calls (including one harness) and four cached relinks. Capture all five executables, the separate rmeta and the rlib, including all native archive members. Establish finite output rules using the new machine's own native, profiled and restored outputs. Record any differences and require a byte-level explanation before measuring.

Use the two inverse eight-pair schedules and bootstrap seeds in `source-and-recipe.json`. Each machine runs one block, after one 30-second entry settle. Preserve both independently warm banks between samples. At the end, converge each bank on the original source, trace a subsequent fresh test build with zero compiler calls and restore the original Cargo. Authenticate both complete blocks and all 32 metrics before comparing either machine. Each machine must have eight wins, exact two-sided sign-test p below 0.01, and a 99% bootstrap lower reduction bound strictly above 1% with 200,000 resamples. Each block produces its own estimate. The endpoint is user-space instructions in the Cargo parent during the dirty test build.
