# Clean archive-writer compiler baseline

The source-built Linux x86-64 compiler is at Rust `5cf1bf9cd196046897a7aeeaf128833d6a464dfe`. Its compiler tree matches published `-18`. Its frontend, driver and standard library were built together in one stage1 configuration, with optimization enabled and PGO and BOLT disabled. The ordinary client used the installed Cargo at `235f9228651b74c591e6f62cae4c9b761448dd2d` and the distributed Wild inode. The release-profile bootstrap donor could not be reached. This baseline supports a same-configuration A/B and source behavior checks. Release performance requires a separately matched release build.

The two-package workspace compiled a public nongeneric function and a reader that calls it. Changing that function from 17 to 29 caused one full producer compile, one reader `-Z link-only` compiler and one real `cc` → `collect2` → Wild. Both root rlibs were 6,264 bytes and their SHA-256 hashes differed. The unchanged third command launched zero compilers and zero linkers. These are structural checks. A process trace and the executable, rlib and Cargo-artifact hashes are bound per phase.

The clean compiler bootstrap succeeded. A first `rustc -vV` on the copied sysroot exited 127 because its build-time shared LLVM library was in the external LLVM directory. A second private sysroot added exactly that already-verified file, and the loader resolved the retained frontend, driver and LLVM. The original failure remains in the raw ledger.

The compiler and standard library build used `x.py build --stage 1 compiler/rustc library` with the pinned external LLVM and the authenticated bootstrap configuration. The private mount had a 12 GiB writable limit. The machine enforced a 25 GiB free-space floor on both storage volumes and a 1 GiB remaining upper limit. The compiler build cache was retained as a hardlink-preserving zstd tar for any separately authorized candidate. The final identity check found both build processes gone and the private mount detached.

Run `python3 -IB verify.py` in this directory to check the projection and manifest. The original process streams and filesystem paths are retained privately.
