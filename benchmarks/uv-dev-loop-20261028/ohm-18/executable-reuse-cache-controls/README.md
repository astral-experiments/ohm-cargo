# Executable reuse after a uv library edit

The first comparison on Ohm -18 stopped before timing. Both normal executables and all 256 codegen objects matched, but the libraries contained different compiler metadata. The field-level comparison accounts for all 8,365 different bytes. [Original traces and admission](original-zero-row.zip) · [Zero-row receipt](original-zero-row.json) · [Metadata analysis](exhaustive.json)

Two cache histories were then crossed with the two Cargo drivers. Each starting cache was built twice with control Cargo and once with candidate Cargo. On the same starting cache, both drivers produced matching library metadata, codegen and executables. Changing the starting cache changed the metadata with either driver. The candidate skipped the uvx compiler and linker when its cache contained the unused-library record. The six retained observations took seven launches. The first launch stopped before raw capture and has a separate trace and restoration receipt. [All six observations](six-controls.md)

The compact archive includes the commands, per-process traces, product digests, excluded-launch record and a standalone scorer. The original content-addressed store holds another 1,953,322,256 bytes of raw products. The compact replay consults only its extracted files and the Python standard library. A full-object verification also accepts that store when supplied. [Download the archive](ohm18-uv-executable-reuse-crossed-controls.tar.zst) · [Archive checksum](package-receipt.json) · [Independent replay](compact-rescore.json)

```sh
tar --zstd -xf ohm18-uv-executable-reuse-crossed-controls.tar.zst
cd ohm18-uv-executable-reuse-crossed-controls
python3 -I -B verify.py
```

The upstream search compared 319 Ohm Cargo commits. All 89 versions of the existing self-library helper restrict reuse to integration tests. [Source census and related pull requests](upstream/README.md)
