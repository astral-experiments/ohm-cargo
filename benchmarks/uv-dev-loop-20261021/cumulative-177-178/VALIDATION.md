# Validation scope

The completed-batch audit verifies fixed counts/seeds, balanced orders,
unchanged variant and recorded-input hashes, all 56 instruction invocations,
all 1,024 native subruns, native group sums, and fresh prepare/timed logs. The
2,620 transferred native files match three separate transfer manifests.
Successful preflight execve paths contain only taskset and the canonical Cargo
executable; no compiler, linker, build-script or test process ran in those
traced fresh invocations. Every test workload uses --no-run. uv remains at
3d82a6ad5a7eab8c68236553b7846517767c4b61 with a clean source tree.

The combined production binary compiled successfully, and its source tree,
build inputs, actual compiler settings, source patch and debug-strip allocated
sections were verified. Both variants were installed at the same canonical
Cargo path, with common source, target and compiler paths. This evidence
includes fresh Ohm-enabled uv preflights for the exact combined binary. It
does not claim that the individual changes' earlier integration suites were
rerun against this exact combination.

Build settings approximate production: stock Rust 1.99.0, optimization level
3, ThinLTO, one codegen unit, debuginfo 1, incremental disabled, all-static and
ohm-defaults enabled, and no PGO. The same embedded pinned Cargo commit is
preserved for both builds; observed source trees distinguish their actual
contents. The candidate provenance is an immutable snapshot, separate from
the build driver's later mutable overall batch record.

Instruction counts are Callgrind 3.22 Cargo-process userspace Ir with
trace-children=no. They do not count kernel work or child compiler work and
are not native timings. The retained profiler stderr includes the known brk
allocator fallback warning for both variants; attribution and allocator cost
are specific to this instrumented environment. Both use the same normal
SSL_CERT_FILE and SSL_CERT_DIR trust-store locations. The audited shim removes
profiler-injected loader variables before Cargo and child environment handling;
no host security setting or certificate verification was disabled.

The native test interval is positive but its estimate is below the frozen 1%
minimum. The native check interval crosses zero. Both fail the full native
gate and remain visible. No results from the separate changes or later
restacked cohort are pooled into this composition comparison.
