# A first target for eliminating an unchanged Ruff test link

The existing full-workspace Ruff trace linked 50 executables on each unchanged `cargo test --workspace --no-run`. Comparing each actual ELF with the preceding file at the same path, 49 of 50 were byte-identical after the cold build and 48 of 50 after restoring a real edit. The same 47 executables were identical in both comparisons. Their combined size was 3.28 GiB. Both commands also ran one full `ron` compile. [Original trace and physical output inventory](https://github.com/astral-sh/ohm-cargo/tree/eabd0a7a472b89cd718d56f6ff9d77ca047e4ed5/benchmarks/ruff-dev-loop-20261027/rc18-r2-ruff-native-qualification)

Start with `ty_server`’s `e2e` integration executable. At 225,211,904 bytes, it was the largest target with matching outputs in both unchanged runs. The real Ruff edit changed its SHA-256 from `273bacc2…` to `fa4f1c07…`. Restoring the edit brought back `273bacc2…`. Its linker ran in all five phases. This gives a target with a known changed output as well as the two redundant-output examples.

The next experiment is to decide before linking, on the published 1.99.0-18 toolchain, whether every consumed link input and effective argument is still valid for that target. An unchanged repeat should skip the link. A private dependency edit that changes the executable must force it and agree with a clean build. An incomplete input record should take the normal link path. Paired timings are warranted once the skipped and mandatory cases both pass.

These counts describe output equivalence from the earlier -18 Cargo pin, `7181bfa6`. The subsequent #263 workspace-exclusion change was qualified separately. Output equivalence alone cannot establish that reusing an executable is sound or predict a time saving.

Run `python3 -IB compare.py /path/to/native.tar.xz` on the archived trace and compare stdout with `result.json`. The script checks the archive SHA-256, the compiler and linker process counts, and the SHA-256 and size at each destination.
