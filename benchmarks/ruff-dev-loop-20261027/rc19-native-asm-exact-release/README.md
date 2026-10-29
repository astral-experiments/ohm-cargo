# Linux source qualification of Rust ca780121 and Cargo 2447f7f4

The candidate produced a stale executable in the assembler test. A genuine public Rust edit and a change to a byte loaded by assembler `.incbin` left the warm program printing 17. An independent empty build printed 29. Removing the assembler input also succeeded on the warm default path. The default Rust job reused cached codegen and executed the stock Wild linker. Both nonincremental defaults-off builds re-read the assembler operand and matched their empty controls.

The independent native-archive test exercised a different input. Changing a native static archive returned 29 after the same kind of Rust edit. The complete edited executable matched its forced and empty builds byte for byte. Replacing the archive with malformed data failed all three builds. The genuine no-op kept its prior executable and launched no Rust compiler or linker.

The two publication orders in the inherited-trait test produced the same E0034 diagnostic on edit, unchanged repeat and empty build. The failed-producer case recovered on the first revert. Killing an actual producer compiler after its consumer had committed recovered the original executable on the first unchanged-source retry. The separate changed input returned 29. Both FIFO error-path controls failed promptly with exit 101. The seven check-only commands covered a private body change, two job-free repeats, and a public signature error with equal warm and empty E0061.

The Rust frontend, driver and 53 target standard-library files came from an optimized Linux x86_64 stage1 bootstrap of the exact Rust commit. The bootstrap used the retained LLVM and did not apply Rust PGO or BOLT. The exact Cargo executable was built separately with release PGO. The rustup alias used those artifacts and the existing stock Wild. Complete local process and compiler outputs are bound by SHA-256 in the JSON files. The assembler comparison sets test-profile incremental codegen off in both arms to isolate the Cargo link-only route.

The bootstrap command exited zero. Its first post-build verifier exited 1 because it recognized only single-line successful `execve` records. In the retained trace, PID 352891 starts the stage1 compilation of `core` on line 11135 and completes the syscall successfully on line 11137. A second verifier joined all interrupted calls by PID and rehashed the original compiler, LLVM, driver and all 53 target-library files. Both receipts are included.

Run the field verifier or rerun individual native checks against a private copy of the same SDK. Each output directory must be new. The assembly reproducer records both passing and failing outcomes.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
python3 -IB reproduce-native.py /tmp/new-native-check /path/to/private-sdk absolute
python3 -IB reproduce-check.py /tmp/new-metadata-check /path/to/private-sdk
python3 -IB reproduce-assembly.py /path/to/private-sdk /tmp/new-asm-default --incremental 0 --relationship unused-public
python3 -IB reproduce-assembly.py /path/to/private-sdk /tmp/new-asm-off --incremental 0 --relationship unused-public --defaults-off
```
