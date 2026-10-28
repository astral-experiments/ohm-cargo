# Native admission for the Ruff test-build comparison

Before starting any clock, H5 verified both Cargo executables, the independent seed, the current draft heads and their eight passing CI jobs. The conditional APFS job was skipped on each head. The two binaries compile the same Ruff source with the shipped Ohm compiler and linker. The scheduler change removes one duplicate compiler invocation and link when first selecting the whole workspace.

The verifier checked six native command rosters covering 297 linker invocations. For the 50 workspace outputs they link, the catalog admits only whole-file SHA-256 values reproduced by stock Wild with the original operands at explicit worker counts. The other 60 workspace outputs and all 78 registry outputs retain a single required digest each. Both previously rejected digests were reproduced. The earlier four clock readings stay excluded. This packet contains zero replacement timings.

The verified host record is in admission.json. The immutable source and result commits are in source-bindings.json.
