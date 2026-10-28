# Source of the 45 inputs in Ruff’s first ron observer

On the exact native Ruff test build, the conventional first Make rule had 19 real inputs plus the intentionally missing observer marker. The candidate’s compulsory and optional records were decoded separately. The optional record adds 26 Rust binary inputs. An independent old Cargo plus new compiler run with conventional explicit binary dep-info named the same 45 real paths, sizes and BLAKE3 content digests. The table lists every actual path and its spelling commitment in verified.json.

| Origin | Files | Evidence |
| --- | ---: | --- |
| Rust crate root and its declared modules | 18 | Every source matches the published ron crate byte for byte. File and line identify its actual mod declaration. |
| ron README | 1 | The crate-root doc attribute calls include_str! at src/lib.rs:18. The compiler registers this file in both its SourceMap and generic file_depinfo. |
| SDK Rust metadata | 19 | Binary-only prerequisites nested or requested explicitly, from used crates in the compiler crate store. |
| Non-SDK Rust metadata | 6 | bitflags, once_cell, serde, serde_core, typeid and unicode-ident. |
| Loaded procedural macro | 1 | The compiled serde_derive shared library. |

All 45 have an independent explanation. Zero require a path exclusively registered through proc_macro::tracked::path. The production library and build-script sources of the full serde_derive macro expansion closure contain no direct tracked-path invocation or generated include! source. The earlier GDB observation saw three Span::join calls set the foreign-span marker. It did not install a breakpoint on track_path. The static and physical inputs therefore establish independent membership, while a hypothetical redundant registration is a separate question.

A generic rule that invalidates every file_depinfo entry would also refuse the real Rust include_str! here. A correction targeting user-declared tracked paths can distinguish that callback from built-in source loading. Binary prerequisites need their own guarantee that the digest recorded by rustc belongs to the bytes it actually consumed. Separate synchronized proc-macro library experiments found that embedded Rust metadata can remain byte-identical while its linked C implementation changes.

Use audit.py with --ruff and --rust pointing to repositories containing the pinned commits, --registry-cache pointing to Cargo’s cache directory and --blake3 pointing to an executable that prints the bare BLAKE3 digest of its one file argument. The default inputs.json and make-role-paths.json come from the actual private Rust .d files. They disclose cargo namespace hashes and filenames without private registry hostnames. Full paths remain on the campaign host; the path SHA-256 fields bind their exact spellings. Run verify.py for the standalone offline consistency checks. The archived observation itself and its original verifier are in the [four-arm native evidence](https://github.com/astral-sh/ohm-cargo/tree/450d18c6c08e159e7c21ca809d523e288f5b680c/benchmarks/ruff-dev-loop-20261027/noquery-workspace-h4-original-native).
