# Shared workspace lints

Compare Ohm Cargo `461a3d1007ecc997a6d86c7d75e8b518575c8d90` and `28c2b64e0936098e900c01d864fb0a026233e917` on Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. Both Cargo binaries used the release profile, release incremental compilation, `--features ohm-defaults`, and the same x86-64 Linux Ohm 1.99.0-14 compiler and registry.

The source edit is the `size.rs` hunk from Ruff `438ef334d3`. The 12 edited pairs and 16 fresh pairs used independently counterbalanced arm orders. Each edited run restored the same pre-edit target snapshot and rebuilt exactly `ruff_text_size`. Fresh runs started after both binaries processed the same artifact and had no child processes. The CSV retains the verified Cargo and rustc counts separately.

Use the [two-binary Callgrind harness and edit patch](../borrow-lockfile/) with `--kind edited --pairs 12 --seed 92173` and `--kind fresh --pairs 16 --seed 43281`. Use a dedicated disposable checkout and stable target directory, and set the two Cargo binary paths to the revisions above. On the original host we used a physically isolated, byte-identical copy of the published compiler.
