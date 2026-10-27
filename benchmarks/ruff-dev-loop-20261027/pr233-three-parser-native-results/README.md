# Three held-out Ruff edits on Rust #232 and fixed #233

Arm B runs #232. Arm C runs fixed #233. All four initial build stores were physically separate. Both compiler releases used the same Cargo #254 and bundled Wild binaries. Each mode exposed each release to each source change for the first time, after training only on unmodified Ruff. The command records and linker witnesses below cover the complete working tree. No timing endpoint was registered in this cohort.

Each recorded compiler and Wild invocation is bound to its per-process trace hash. The comparison includes every full and link-only Rust job, including its actual parser dependency, each linked product and the raw executable and ELF section digests. The comparisons for .text and .rodata use section payload bytes. The separate masked digest suppresses only the GNU build ID and .rodata section entry size. All remaining bytes count.

The initial runner stopped before any edits because Cargo puts each compiler release in a separate physical output namespace. The new run starts every state from empty. Cross-release unit rosters use a single exact path-component substitution. The extractor independently reapplies it to every raw Cargo artifact message. The per-arm raw scope, complete remaining path and diagnostic identity, and same-release raw file paths stay visible.

The ordinary Rust callers use the same release and dependency store that emitted the input. The build and test stores have 501 and 619 units. The immediate commands must have zero Rust jobs and zero native links. No Cargo test binaries execute. The historical signed-pattern edit changes both pinned Ruff diagnostics on first exposure and restores them on reversal.

Run python3 -B verify.py in this directory. The included export and physical projection scripts can regenerate these records on the prepared H5 host using the complete private native invocation receipts and registered frozen worker.
