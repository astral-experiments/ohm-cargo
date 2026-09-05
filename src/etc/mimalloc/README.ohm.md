Mimalloc 3.5.1, from Microsoft commit `34fbd7e7cd4627424490afe19b20f8066bfc537d`.

Source: https://github.com/microsoft/mimalloc/tree/34fbd7e7cd4627424490afe19b20f8066bfc537d

The CMake build files, `include`, and `src` directories are copied without changes. The upstream MIT license is in `LICENSE`.

Ohm builds this static allocator for the Apple Silicon Cargo executable. The pinned source matches the allocator used in the native command benchmarks; libmimalloc-sys 0.1.49 bundles mimalloc 3.3.2. Cargo library consumers, credential helpers, and other toolchain executables keep their existing allocator.
