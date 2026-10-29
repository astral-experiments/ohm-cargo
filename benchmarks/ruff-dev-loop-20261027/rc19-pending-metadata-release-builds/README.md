# Matched release-profile Cargo for pending metadata

These Linux x86-64 builds isolate one change in Cargo's compiler fingerprint module. The control source is 235f9228651b74c591e6f62cae4c9b761448dd2d. The candidate is b3360c5eda186845b9a2ba6e5330a97c07d4acf2. Both report the control's release stamp so the version string cannot perturb downstream fingerprints.

| Arm | Executable SHA-256 | Bytes |
| --- | --- | ---: |
| Control | 3a94265b0d3c80afd228f575190a8c291506951b1a77e45bb9bac2aa89387df7 | 43,475,672 |
| Candidate | 51eb6c59a38151fbf1a252d7bc39cb45dfa67482a95b526e1301046bbf593ce9 | 43,475,432 |

Both builds used the exact same PGO profile, Rust compiler, ordinary unprivileged user, trusted filesystem root, release options, canonical build paths, job count and recorded environment. Each of the 3,108 release-source entries was checked against its Git blob and mode. The historical 6aaa263e control used a different registry-artifact path and remains a separate subject.

An independent first build of the candidate matched the control's two rustc argument vectors. Twelve third-party dependency references differed in content across six crates, which disqualified that pair. For the accepted build, we copied the control's completed dependency state to a private tree. All 241 references were byte-checked against the control, and all distinct underlying source and copied files had separate inodes. We removed the two copied Cargo units and binary before invoking the normal locked, offline release build. Cargo compiled the changed project. Both actual rustc argument vectors were identical across the resulting pair. All 239 non-project dependency references matched in path and bytes. The binary's two references to Cargo's own library remained free to reflect the change.

The actual final linker invocations had 411 arguments. All remaining arguments matched after labeling the generated symbols object, raw-dylibs directory and GCC resolution temporary. Their literal names remain committed per arm. Their contents were ephemeral and were not recovered. All 335 explicit non-project linker file operands matched in path and bytes, including 326 Rust archives. The six native search directories supplied 404 matching files. Both executables also report the same seven dynamic library dependencies.

Run the portable checks from this directory.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
```

To check the Git objects and run each ELF, use the optional paths.

```sh
python3 -IB verify.py --checkout /path/to/ohm-cargo --binaries /path/to/parent-of-A-and-B
```

The original native process traces, binaries, private paths and build environment are in the separate private collection. This packet records toolchain and dependency equivalence for a subsequent experiment. It contains no Ruff executions or performance measurements.
