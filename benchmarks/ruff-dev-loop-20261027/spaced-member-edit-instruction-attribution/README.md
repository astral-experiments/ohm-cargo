# Where the changed typeshed build spends its instructions

These are unscored diagnostics for the real Ruff `ty_wasm` edit whose matched release-candidate wall study measured a 6.16% slower individual build and a 22.46% faster edit-plus-repeat loop. B is the canceled RC17 source and C includes the raw-path checksum correction. Both used the same frontend, SDK, linker, upstream Ruff revision and historical typeshed edit. Each cell below compares four source-direction-matched pairs. [Original wall study and tool identities](https://github.com/astral-sh/ohm-cargo/tree/d6acc7673a727ea16fa49805f0f837fe17ecd2f0/benchmarks/ruff-dev-loop-20261027/spaced-ruff-member-edit-wall-v2-results)

| Process | Collector | C minus B instruction count, paired range |
| --- | --- | ---: |
| Cargo supervisor | Callgrind Ir | +2.66M to +3.04M |
| Typeshed ZIP build script | DynamoRIO | −0.06M to +1.41M |
| ty_vendored rustc | DynamoRIO | +0.87M to +4.07M |
| ty_wasm rustc | DynamoRIO | −126.48M to +149.07M |

The ZIP builder was the same executable in both arms and took about 10.71 billion instructions. The corrected compiler reads the generated ZIP a second time to checksum its actual pathname. An isolated dep-info command with the exact 1,478,740-byte input held the canceled compiler constant. Providing an escaped-name decoy with identical bytes made it checksum the same payload and added 3,856,368 to 3,856,373 Callgrind instructions. The fixed compiler checksummed the real bytes in both conditions. The 16 calls are in `isolated-real-zip.json`.

A separate experiment held the corrected compiler and Cargo constant. One working copy was allowed its normal, fully fresh repeat. In a second copy two private Cargo fingerprints were removed before the preceding repeat, which forced the same two full compilers and one Wild link without removing rustc incremental state. Both histories reached the higher instruction count in ty_wasm on restoration. Counts for ty_wasm differed by −11.16M to +8.15M between the paired histories. The process-level observations do not account for the full wall difference. Only the separate original study tested the wall-time hypothesis.

Fourteen additional ordinary Cargo commands checked a fully unspaced layout. Each changed source direction used two full rustcs and one Wild link. On each trained repeat all 304 Cargo artifacts were fresh with zero compiler or linker jobs. Both arms agreed on the raw native shared object, ZIP and the bytes returned by an ordinary external Rust caller. The spaced experiments also validate typed artifacts and a real caller after each edit and its following repeat. `sampled-resources.json` contains separate native process and I/O observations.

The Cargo-only and child measurements used different collectors in separate real Cargo invocations. Their counts are reported separately. An initial nested-instrumentation launch failed, and the first Cargo-only Callgrind launch stopped before Cargo's startup certificate configuration completed. Ordinary Cargo emitted the two effective certificate paths, preserved in `ssl-native-control/`. Supplying those identical settings to both arms allowed all eight Cargo-only measurements to complete. The failed attempts remain in this packet.

Run `python3 -B verify.py` from any directory to verify every included digest, source/output and count gate, and print the paired ranges. The source workers are diagnostic scripts tied to the recorded bench environment. All dataset paths in SHA256SUMS are relative to this directory.
