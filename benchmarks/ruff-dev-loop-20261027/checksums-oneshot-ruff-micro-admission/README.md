# Local host and native admission for the BLAKE3 checksum screen

The shared optimized helper runs the two checksum implementations from Cargo 105fe8286be. The source, exact order, four-part threshold and initial rejected packet-pipe sketch are pinned in the [source registration](https://github.com/astral-sh/ohm-cargo/tree/32c4f9da05956359fbd8d660c712c846fd8ff01f/benchmarks/ruff-dev-loop-20261027/checksums-oneshot-ruff-source-plan).

Both ordinary commands and both syscall audits produced the same native output. Each traced process opened and closed 4,952 regular files and issued 10,152 requests for 65,536 bytes. The per-descriptor request, byte-count and EOF sequences agree in full. The raw logs omit string buffers while preserving each requested and returned size. The portable C reference was compiled directly from locked BLAKE3 1.8.5 and its ordered digest matched the independently captured reference in the source registration.

The host record binds the artifact identities, ELF dependencies, counter search path, affinity and child environment. CPU 14 is a separate virtual core on charlie-oss-8. The worker reserves it with an advisory lock shared by this study. Normal machine services may run. The endpoint counts application instructions and excludes elapsed time. The native admission contains zero instruction measurements.

Run `python3 -B verify.py` from an offline copy to check the manifest, ledgers, source membership, executable identities and ordinary outputs. The actual local executable and data paths are recorded in host.json. The prospective measured command requires a separate explicit release from the coordinator.
