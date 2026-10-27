# Ruff build and test compilation with observed source spans

The previous [compiler-only plan](../private-location-regression/plan.json) requires each immediate repetition to be fresh. The compiled Rust-only intermediate reached 501/501 for build. One genuine reader in the registry `ron` dependency caused 56 of 619 test-build units to report dirty on an unchanged `cargo test --no-run`. The companion Cargo prototype trained the reader and restored 619/619 fresh. No compiler-only timing was scored from a failed endpoint.

The prospective plan in this directory gives both compiler arms the same Cargo. It records the first training build separately, and scores ordinary command wall time only after a fully fresh run. Independent warmed directories and native process traces cover the original private doc and parser edits and a behavioral Ruff lint change.

The source evidence archives include verifiers and startup instructions. The first isolates a stale incremental producer source checksum as the cause of differing proc-macro output. The second verifies the corrected compiler against all eleven CI-selected run-make tests, a transitive generated proc-macro, ordinary warm and clean Cargo commands, and the original metadata-prefix controls.
