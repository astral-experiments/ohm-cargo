# A rejected shortcut omitted Wild’s requested layout

The small Linux workspace builds an rlib and cdylib. Its integration test starts with `#![cfg(target_arch = "wasm32")]`. On x86-64 the test executable reports zero tests. The reference is Cargo d38fdd0250. The rejected Cargo revision is 1b72ade16f.

After warming the test, the fixture changes a library implementation and sets `WILD_WRITE_LAYOUT=1` for `cargo test --no-run`. The reference runs the API link and writes the requested layout. The rejected prototype reuses the API executable without running its rustc or linker, and the layout never appears. The reference and rejected records come from independent native workspaces. Their ELF hashes identify the individual artifacts.

Two further reference commands change only a directly declared rlib. The first adds `libutil.so` ahead of the system library in an isolated SDK copy. The second substitutes the exact previously resolved `libutil.a` inside a private mount namespace. Both reach and fail in the API link. Removing each altered input restores the ordinary executable. When the test requests a map and dependency file through `RUSTFLAGS` or target configuration, the ordinary command recreates both after they are deleted.

The observations retain only source and subject identities, phase names, process names, exit status, test listings, and artifact sizes and hashes. These are correctness controls and carry no performance estimate.
