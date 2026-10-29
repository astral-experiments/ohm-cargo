# A dirty Rust integration test can depend on an implicit system library

A one-package integration test has no dependencies or build script. Its source contains one Rust test and one `println!`. Changing a private function in the package library caused published-style Cargo `29e8dbd29` to reuse the old executable after a simulated system library update. Its Rust compiler accurately reported the package library unused. GCC still supplies `-lgcc_s` when linking the test.

| First test build after the Rust edit | Previous whole-test reuse | Defaults disabled | Broader cached-codegen fix | Independent empty builds |
| --- | --- | --- | --- | --- |
| Pure Rust, valid replacement system linker script | Old executable exits 0 | Rebuilt executable exits 83 | Rebuilt executable exits 83 | Exit 83 with both linkers |
| Pure Rust, malformed replacement | Cargo succeeds twice | Cargo exits 101 twice | Cargo exits 101 twice | Both linkers fail |
| Test requests an ordinary static C library, 17 changes to 29 | Old executable prints 17 | Prints 29 | Prints 29 | Prints 29 |
| Malformed static C library | Cargo succeeds twice | Cargo exits 101 twice | Cargo exits 101 twice | Link fails |

On both corrected default builds the Rust edit ran the integration target's cached `rustc -Z link-only` and one actual packaged Wild. The immediate valid unchanged repeat ran zero test compilers and linkers. Without a Rust edit, changing an untracked external library left an already-fresh target alone. The regression uses the ordinary Rust edit that would relink under the defaults-disabled control. No measurements of elapsed time were taken.

## Native inputs and isolation

The pure-Rust case keeps the ordinary `libgcc_s.so` script and adds a private observer object to it. That object requests process exit 83 from ELF preinitialization. The malformed replacement makes the linker report an error. The explicit C case puts a uniquely named archive in the default system search path. It contains a single function returning 17 or 29. All source files are recorded in `records.json.gz`. The fixtures specify no Cargo configuration, extra compiler or linker flags, compiler wrappers, native search environment or `build.rs`.

Each experiment gets a private Linux mount namespace. The original library directory is a read-only lower layer. Only the task's private upper layer contains replacement files. After every namespace exited, the host's original GCC script still had SHA-256 `69a56a9993b7729b29b274e65016031c81f2397f176ed5ad44d59bd50425e0bd`, and the unique C archive was absent from the host. Cargo, rustc, the linker and test programs ran as an ordinary user.

The pure-Rust baseline used release-profile PGO Cargo built from `29e8dbd291cd79fd8c1ba46f86b3dc333d23cde7`, SHA-256 `fcb1960fa700069b2cf9634526e2cc1a7d7aa0e68d00fc358075e6b7a8fd87d0`. The explicit C baseline used the separately verified development image `00d75d89b28a`. The corrected image was the development build `99383612a7a0`. All used exactly the same `5e3de497` rustc. The defaults-disabled comparison selected GNU ld. The defaults-enabled comparisons used the packaged Wild binary.

## Verification

The archive contains path-normalized stdout, stderr, native program output and actual process traces for all 96 Cargo commands. Original and normalized stream digests are retained. The verifier reopens 52 physical test links, 78 executed test programs and 18 real linker errors. It checks source hashes, the absence of build-script events, the link-only rustc command and true no-op runs. Run it without privileges.

```sh
sha256sum -c --quiet SHA256SUMS && python3 -IB verify.py
```

To reconstruct the archive from the four originally retained private experiment directories, run `python3 -IB collect.py /path/to/raw /new/output`. The ordinary staged-provider reproduction offers a separate end-to-end example that requires no private system mount. [Three-release fixture and replay](https://github.com/astral-sh/ohm-cargo/tree/f47f7413b0e99381ea6ac4ded02162919ecee3f8/benchmarks/ruff-dev-loop-20261027/rc19-transitive-native-link-release-hold)
